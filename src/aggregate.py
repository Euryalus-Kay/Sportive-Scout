"""Turns moment logs into team stats.

Every position here is relative to the analyzed team in that game:
zone x 1-6 (6 = the end they attack), zone y 1-4 (1 = their left touchline),
and xy 0-100 the same way.

A team "profile" combines every game in games.yaml where that team is the
analyzed team.
"""
from collections import Counter

import numpy as np

from src import config
from src.analyzer import load_log

PASS1_INTERVAL = 4          # seconds between Pass 1 frames (see extract.py)
GOAL_MATCH_WINDOW = 30      # seconds: a logged goal this close to a games.yaml goal is the same goal


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

def game_stats(game, logs_dir=config.LOGS_DIR):
    """All stats for one game, from the analyzed team's point of view."""
    log = load_log(game["id"], logs_dir)
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
        "events": [],
        "players": Counter(),
    }
    for e in wide:
        _add_frame(stats, e)
    stats["events"] = _collect_events(game, log)
    stats["shots"] = _shots_with_yaml_goals(game, stats["events"])
    return stats


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
    seen_goals = set()
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
                key = (ev.get("team"), e["timestamp"])
                if key in seen_goals:
                    continue
                seen_goals.add(key)
            ev.update({
                "game_id": game["id"],
                "timestamp": e["timestamp"],
                "video_seconds": e["video_seconds"],
                "game_minute": e["game_minute"],
                "zone": e.get("ball_zone"),
            })
            if is_shot and not ev.get("xy"):
                ev["xy"] = e.get("ball_xy") or (zone_center(e["ball_zone"]) if e.get("ball_zone") else None)
            events.append(ev)
    return events


def _pass2_windows(log):
    """(start, end) video seconds covered by each Pass 2 batch."""
    by_batch = {}
    for e in log:
        if e["source"] == "pass2":
            by_batch.setdefault(e["batch"], []).append(e["video_seconds"])
    return [(min(v), max(v)) for v in by_batch.values()]


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
        shots.append({
            "type": "shot", "team": team, "outcome": "goal",
            "position": goal.get("position", "unknown"),
            "build_up": goal.get("how", "unknown"),
            "game_id": game["id"],
            "timestamp": goal.get("time"),
            "video_seconds": t,
            "game_minute": config.game_minute(game, t) if t is not None else None,
            "zone": None, "xy": None, "from_yaml": True,
        })
    return shots


# ---------- whole-team profile ----------

def team_profile(cfg, team_name, logs_dir=config.LOGS_DIR):
    """Combine every game where `team_name` is the analyzed team."""
    games = [g for g in cfg["games"] if g.get("analyzed_team_name") == team_name]
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
    return {k: game.get(k) for k in ("id", "analyzed_team_name", "other_team_name",
                                      "final_score", "playoff", "opponent_strength", "notes")}


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
