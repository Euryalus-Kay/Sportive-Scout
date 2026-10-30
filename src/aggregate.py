"""Turns moment logs into team stats.

Every position here is relative to the analyzed team in that game:
zone x 1-6 (6 = the end they attack), zone y 1-4 (1 = their left touchline),
and xy 0-100 the same way.

A team "profile" combines every game in games.yaml that shows that team: as
the analyzed team, or as the other team (the same log, mirrored).
"""
from collections import Counter

import numpy as np

from src import config
from src.analyzer import load_log

PASS1_INTERVAL = 4          # seconds between Pass 1 frames (see extract.py)
GOAL_MATCH_WINDOW = 30      # seconds: goals by one team this close together are the same goal
PASS2_GAP = 5               # seconds: Pass 2 frames further apart than this are separate moments
TIMELINE_STEP = 5           # minutes per timeline bar
TIMELINE_BINS = 19          # 0-5', 5-10', ... 85-90', 90+'


def empty_heat():
    """4 rows (width, y) x 6 columns (length, x)."""
    return np.zeros((4, 6))


def zone_center(zone):
    """Middle of a 6x4 zone in 0-100 coordinates."""
    x, y = zone
    return [(x - 0.5) * 100 / 6, (y - 0.5) * 100 / 4]


def side_of(y):
    """Zone row -> "left" / "center" / "right" (from the analyzed team's view)."""
    return "left" if y == 1 else "right" if y == 4 else "center"


# ---------- one game ----------

SWAP = {"analyzed_team": "other_team", "other_team": "analyzed_team"}
SWAP_STRENGTH = {"weaker": "stronger", "stronger": "weaker", "similar": "similar"}


def mirror_game(game):
    """The same film seen from the other team's side: names, kits, goals and directions swapped.

    One analyzed video holds both teams, so a team that is the *other* team in a film
    still gets that film in its profile, read from the same log (see mirror_entry).
    """
    m = dict(game)
    m["analyzed_team_name"], m["other_team_name"] = game.get("other_team_name"), game.get("analyzed_team_name")
    kits = game.get("kit_colors") or {}
    m["kit_colors"] = {"analyzed_team": kits.get("other_team"), "other_team": kits.get("analyzed_team")}
    m["attacking_direction"] = "left" if game.get("attacking_direction", "right") == "right" else "right"
    m["opponent_strength"] = SWAP_STRENGTH.get(game.get("opponent_strength"), "similar")
    m["goal_times"] = [{**g, "team": SWAP.get(g.get("team", "analyzed_team"), "other_team")}
                       for g in game.get("goal_times", [])]
    score = str(game.get("final_score") or "")
    m["final_score"] = "-".join(reversed(score.split("-"))) if score.count("-") == 1 else score
    m["mirrored"] = True
    return m


def mirror_entry(e):
    """One logged frame from the other team's side: the pitch turns 180 degrees, team labels swap."""
    flip = lambda xy: [100 - xy[0], 100 - xy[1]] if xy else None
    return {
        **e,
        "possession": SWAP.get(e.get("possession"), e.get("possession")),
        "ball_zone": [7 - e["ball_zone"][0], 5 - e["ball_zone"][1]] if e.get("ball_zone") else None,
        "ball_xy": flip(e.get("ball_xy")),
        "analyzed_team_shape": e.get("other_team_shape"), "other_team_shape": e.get("analyzed_team_shape"),
        "analyzed_team_block": e.get("other_team_block"), "other_team_block": e.get("analyzed_team_block"),
        "events": [{**ev, "team": SWAP.get(ev.get("team"), ev.get("team")),
                    **({"xy": flip(ev["xy"])} if ev.get("xy") else {})} for ev in e.get("events", [])],
        "players": [],      # jersey numbers aren't tied to a team, so they stay with the analyzed side
    }


def team_games(cfg, team_name):
    """Games in a team's profile: films where it's the analyzed team, then films where it's the
    other team (mirrored), unless that video is already in the list."""
    direct = [g for g in cfg["games"] if g.get("analyzed_team_name") == team_name]
    files = {g.get("file") for g in direct}
    return direct + [mirror_game(g) for g in cfg["games"]
                     if g.get("other_team_name") == team_name and g.get("file") not in files]


def retimed(game, log):
    """Log entries with game minutes worked out from games.yaml as it is now.

    Minutes are stored when a frame is logged; recomputing them means a corrected
    kickoff time or half length applies without analyzing the film again.
    """
    return [{**e, "game_minute": config.game_minute(game, e["video_seconds"], half=e["half"])}
            if e.get("video_seconds") is not None and e.get("half") in (1, 2) else e for e in log]


def game_stats(game, logs_dir=None):
    """All stats for one game, from the analyzed team's point of view."""
    log = retimed(game, load_log(game["id"], logs_dir))
    if game.get("mirrored"):
        log = [mirror_entry(e) for e in log]
    scan = [e for e in log if e["source"] == "pass1" and e["half"] in (1, 2)]
    wide = [e for e in scan if e["view"] == "wide"]
    stats = {
        "game_id": game["id"],
        "frames_logged": len(scan),
        "frames_wide": len(wide),
        "minutes_covered": len(scan) * PASS1_INTERVAL / 60,
        "avg_confidence": float(np.mean([e["confidence"] for e in wide])) if wide else 0.0,
        "possession": Counter(e["possession"] for e in wide),
        "heat_all": empty_heat(),
        "heat_in": empty_heat(),
        "heat_out": empty_heat(),
        "shape_in": Counter(),
        "shape_out": Counter(),
        "block_in": Counter(),
        "block_out": Counter(),
        "other_shape_in": Counter(),
        "other_shape_out": Counter(),
        "attack_side": Counter(),       # where they have the ball in the final third
        "defend_side": Counter(),       # where opponents have the ball in their defensive third
        "timeline": empty_timeline(),   # possession and territory per 5 minutes
        "events": [],
        "players": Counter(),
    }
    for e in wide:
        _add_frame(stats, e)
        _add_to_timeline(stats["timeline"], e)
    stats["events"] = _collect_events(game, log)
    stats["shots"] = _shots_with_score_goals(game, _shots_with_yaml_goals(game, stats["events"]))
    return stats


def empty_timeline():
    """Per 5-minute bin: frames in / out of possession, in the final third, in danger."""
    return np.zeros((TIMELINE_BINS, 4))


def timeline_bin(minute):
    return min(int((minute or 0) // TIMELINE_STEP), TIMELINE_BINS - 1)


def _add_to_timeline(timeline, e):
    """Columns: 0 = they have the ball, 1 = opponents have it, 2 = they have it in the
    final third, 3 = opponents have it in their defensive third."""
    row = timeline_bin(e["game_minute"])
    x = e["ball_zone"][0] if e.get("ball_zone") else None
    if e["possession"] == "analyzed_team":
        timeline[row, 0] += 1
        if x is not None and x >= 5:
            timeline[row, 2] += 1
    elif e["possession"] == "other_team":
        timeline[row, 1] += 1
        if x is not None and x <= 2:
            timeline[row, 3] += 1


def _add_frame(stats, e):
    """Add one wide-view frame to heat maps, shapes and sides."""
    stats["players"].update(e.get("players", []))
    pos = e["possession"]
    if pos == "analyzed_team":
        stats["shape_in"][e["analyzed_team_shape"]] += 1
        stats["block_in"][e["analyzed_team_block"]] += 1
        stats["other_shape_out"][e["other_team_shape"]] += 1
    elif pos == "other_team":
        stats["shape_out"][e["analyzed_team_shape"]] += 1
        stats["block_out"][e["analyzed_team_block"]] += 1
        stats["other_shape_in"][e["other_team_shape"]] += 1
    if not e.get("ball_zone"):
        return
    x, y = e["ball_zone"]
    stats["heat_all"][y - 1, x - 1] += 1
    if pos == "analyzed_team":
        stats["heat_in"][y - 1, x - 1] += 1
        if x >= 5:
            stats["attack_side"][side_of(y)] += 1
    elif pos == "other_team":
        stats["heat_out"][y - 1, x - 1] += 1
        if x <= 2:
            stats["defend_side"][side_of(y)] += 1


def _collect_events(game, log):
    """Every event with its time and place. Pass 2 replaces Pass 1 inside its windows."""
    windows = _pass2_windows(log)
    events = []
    goal_times = []                     # (team, video seconds) of goals already counted
    for e in log:
        if e["half"] not in (1, 2):
            continue
        in_window = any(lo <= e["video_seconds"] <= hi for lo, hi in windows)
        for ev in e.get("events", []):
            ev = dict(ev)
            is_shot = ev["type"] in ("shot", "goal")
            # Shots inside a Pass 2 window are taken from Pass 2 only (more accurate).
            if is_shot and e["source"] == "pass1" and in_window:
                continue
            if ev["type"] == "goal":
                ev["type"], ev["outcome"] = "shot", "goal"
            if ev["type"] == "shot" and ev.get("outcome") == "goal":
                # The same goal is often visible on several frames (1 s apart in Pass 2).
                if any(team == ev.get("team") and abs(t - e["video_seconds"]) <= GOAL_MATCH_WINDOW
                       for team, t in goal_times):
                    continue
                goal_times.append((ev.get("team"), e["video_seconds"]))
            ev.update({
                "game_id": game["id"],
                "timestamp": e["timestamp"],
                "video_seconds": e["video_seconds"],
                "half": e["half"],
                "game_minute": e["game_minute"],
                "late": config.is_late(game, e["game_minute"]),
                "zone": e.get("ball_zone"),
            })
            if is_shot and not ev.get("xy"):
                ev["xy"] = e.get("ball_xy") or (zone_center(e["ball_zone"]) if e.get("ball_zone") else None)
            events.append(ev)
    return events


def _pass2_windows(log):
    """(start, end) video seconds covered by each run of 1-second Pass 2 frames."""
    windows = []
    for t in sorted(e["video_seconds"] for e in log if e["source"] == "pass2"):
        if windows and t - windows[-1][1] <= PASS2_GAP:
            windows[-1][1] = t
        else:
            windows.append([t, t])
    return [tuple(w) for w in windows]


def _shots_with_score_goals(game, shots):
    """Goals the final score says happened but no frame or games.yaml entry caught.

    Each is added once, with no time or place ("time unknown"), so goal counts match the score.
    """
    score = str(game.get("final_score") or "").replace(" ", "")
    parts = score.split("-")
    if len(parts) != 2 or not all(x.isdigit() for x in parts):
        return shots
    shots = list(shots)
    for team, total in zip(("analyzed_team", "other_team"), map(int, parts)):
        found = sum(1 for s in shots if s.get("outcome") == "goal" and s.get("team") == team)
        shots += [{"type": "shot", "team": team, "outcome": "goal", "position": "unknown", "build_up": "unknown",
                   "game_id": game["id"], "timestamp": None, "video_seconds": None, "half": None,
                   "game_minute": None, "late": False, "zone": None, "xy": None, "from_score": True}
                  for _ in range(total - found)]
    return shots


def _shots_with_yaml_goals(game, events):
    """All shots, plus any goal from games.yaml that was never logged.

    games.yaml goals can say `team`, `position` and `how` so a goal is never lost.
    """
    shots = [e for e in events if e["type"] == "shot"]
    for goal in game["goal_times"]:
        team = goal.get("team", "analyzed_team")
        t = goal.get("seconds")
        logged = any(s.get("outcome") == "goal" and s.get("team") == team
                     and t is not None and abs(s["video_seconds"] - t) <= GOAL_MATCH_WINDOW
                     for s in shots)
        if logged:
            continue
        minute = config.game_minute(game, t) if t is not None else None
        shots.append({
            "type": "shot", "team": team, "outcome": "goal",
            "position": goal.get("position", "unknown"),
            "build_up": goal.get("how", "unknown"),
            "game_id": game["id"],
            "timestamp": goal.get("time"),
            "video_seconds": t,
            "half": config.half_for(game, t) if t is not None else None,
            "game_minute": minute,
            "late": config.is_late(game, minute),
            "zone": None, "xy": None, "from_yaml": True,
        })
    return shots


# ---------- whole-team profile ----------

def team_profile(cfg, team_name, logs_dir=None):
    """Combine every game that shows `team_name` (as the analyzed team or, mirrored, the other team)."""
    games = team_games(cfg, team_name)
    per_game = [game_stats(g, logs_dir) for g in games]
    profile = {
        "team": team_name,
        "games": [_context(g) for g in games],
        "frames_logged": sum(s["frames_logged"] for s in per_game),
        "frames_wide": sum(s["frames_wide"] for s in per_game),
        "minutes_covered": sum(s["minutes_covered"] for s in per_game),
    }
    profile["avg_confidence"] = (
        sum(s["avg_confidence"] * s["frames_wide"] for s in per_game) / profile["frames_wide"]
        if profile["frames_wide"] else 0.0)
    for key in ("heat_all", "heat_in", "heat_out"):
        profile[key] = sum((s[key] for s in per_game), empty_heat())
    profile["timeline"] = sum((s["timeline"] for s in per_game), empty_timeline())
    for key in ("possession", "shape_in", "shape_out", "block_in", "block_out",
                "other_shape_in", "other_shape_out", "attack_side", "defend_side", "players"):
        profile[key] = sum((s[key] for s in per_game), Counter())
    events = [e for s in per_game for e in s["events"] if e["type"] != "shot"]
    shots = [e for s in per_game for e in s["shots"]]
    profile["events_for"] = [e for e in events if e.get("team") == "analyzed_team"]
    profile["events_against"] = [e for e in events if e.get("team") == "other_team"]
    profile["shots_for"] = [s for s in shots if s.get("team") == "analyzed_team"]
    profile["shots_against"] = [s for s in shots if s.get("team") == "other_team"]
    _add_summary(profile)
    return profile


def _context(game):
    return {k: game.get(k) for k in ("id", "analyzed_team_name", "other_team_name", "final_score",
                                      "playoff", "opponent_strength", "notes", "mirrored")}


def _add_summary(p):
    """Simple numbers the interface and insights use directly."""
    poss = p["possession"]
    total = poss["analyzed_team"] + poss["other_team"]
    p["possession_pct"] = 100 * poss["analyzed_team"] / total if total else None
    p["per90"] = 90 / p["minutes_covered"] if p["minutes_covered"] else 0
    p["formation_in"] = _top(p["shape_in"])
    p["formation_out"] = _top(p["shape_out"])
    p["block_out_main"] = _top(p["block_out"])
    p["goals_for"] = [s for s in p["shots_for"] if s.get("outcome") == "goal"]
    p["goals_against"] = [s for s in p["shots_against"] if s.get("outcome") == "goal"]
    p["goals_by_position"] = Counter(s.get("position") or "unknown" for s in p["goals_for"])
    p["shots_by_position"] = Counter(s.get("position") or "unknown" for s in p["shots_for"])
    p["turnovers"] = events_of(p["events_for"], "turnover")
    p["rates"] = _rates(p)


def _rates(p):
    """Per-90 numbers and shares used to compare two teams side by side."""
    per90 = p["per90"]
    count = lambda kind: len(events_of(p["events_for"], kind)) * per90
    in_poss = p["timeline"][:, 0].sum()
    return {
        "possession": p["possession_pct"] or 0.0,
        "shots_90": len(p["shots_for"]) * per90,
        "shots_against_90": len(p["shots_against"]) * per90,
        "on_target_pct": _pct([s for s in p["shots_for"] if s.get("outcome") in ("goal", "on_target")],
                              p["shots_for"]),
        "box_shots_pct": _pct([s for s in p["shots_for"] if in_box(s.get("xy"))],
                              [s for s in p["shots_for"] if s.get("xy")]),
        "final_third_pct": float(100 * p["timeline"][:, 2].sum() / in_poss) if in_poss else 0.0,
        "presses_90": count("press"),
        "crosses_90": count("cross"),
        "long_balls_90": count("long_ball"),
        "turnovers_own_half_90": len([t for t in p["turnovers"] if t.get("zone") and t["zone"][0] <= 3]) * per90,
        "high_block_pct": share(p["block_out"], "high"),
        "low_block_pct": share(p["block_out"], "low"),
    }


def in_box(xy):
    """True when a relative 0-100 spot is inside the attacked penalty box."""
    return bool(xy) and xy[0] >= 100 - 16.5 * 100 / 105 and abs(xy[1] - 50) <= 20.16 * 100 / 68


def _pct(part, whole):
    return 100 * len(part) / len(whole) if whole else 0.0


def _top(counter):
    """Most common real value in a Counter (ignores None)."""
    for value, _ in counter.most_common():
        if value:
            return value
    return None


def events_of(events, kind, **match):
    """Filter events by type and any extra fields, e.g. events_of(ev, "set_piece", subtype="corner")."""
    return [e for e in events if e["type"] == kind
            and all(e.get(k) == v for k, v in match.items())]


def share(counter, key):
    """Percent of a Counter's total that is `key`."""
    total = sum(v for k, v in counter.items() if k)
    return 100 * counter[key] / total if total else 0.0
