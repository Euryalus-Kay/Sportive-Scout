"""Strengths, weaknesses and the matchup, as plain insights.

Each finding comes from a simple rule over a team profile (see aggregate.py)
and is written as a number with a short line, e.g. stat "59%", label "of
final-third possession down the left", basis "143 frames". The app shows
insights only. The older coaching advice is still kept in `action` for the
markdown game plan, but nothing on screen tells the coach what to do.

Findings carry `tags`, always written from the ATTACKING team's point of view
(e.g. "attack_left" means "attacks get through down the attacker's left").
That lets an opponent weakness be matched to one of our strengths.
"""
from src.aggregate import events_of, share
from src.positions import POSITION_GROUPS, position_group

STRONG, POSSIBLE, ONCE = "strong pattern", "possible pattern", "seen once"
OPPOSITE = {"left": "right", "right": "left", "center": "center"}


def evidence_label(count):
    """Strong pattern (5+), possible pattern (2-4) or seen once."""
    if count >= 5:
        return STRONG
    if count >= 2:
        return POSSIBLE
    return ONCE


def finding(kind, stat, label, basis, count, items=(), tags=(), action=""):
    """One strength or weakness: a stat, what it measures, and what it is based on.

    `moments` keeps the game and video time of each piece of evidence, so the
    app can show the frame or a clip of it.
    """
    with_time = [e for e in items if e.get("timestamp")]
    moments = [{"game_id": e.get("game_id"), "seconds": e.get("video_seconds"),
                "timestamp": str(e["timestamp"])} for e in with_time]
    return {"kind": kind, "stat": stat, "label": label, "basis": basis,
            "title": f"{stat} {label}", "detail": basis, "count": count,
            "evidence": evidence_label(count), "timestamps": [m["timestamp"] for m in moments][:12],
            "moments": moments[:12], "tags": list(tags), "action": action}


def per90(p, n):
    return n * p["per90"]


def _frames(n):
    return f"{n} frame" + ("" if n == 1 else "s")


def _say(n, one, many):
    """The right wording for a count: _say(1, "shot", "shots") -> "shot"."""
    return one if n == 1 else many


# ---------- strengths ----------

def strengths(p):
    out = []
    poss = p["possession_pct"]
    if poss is not None and poss >= 55:
        out.append(finding(
            "strength", f"{poss:.0f}%", "possession", f"from {_frames(_poss_frames(p))}",
            p["possession"]["analyzed_team"], tags=["possession"],
            action="Stay compact and let them pass in harmless areas; win it in midfield "
                   "and break fast before they can reset."))

    side, pct = _main_side(p["attack_side"])
    if side and pct >= 45 and p["attack_side"][side] >= 5:
        where = "through the middle" if side == "center" else f"down the {side}"
        out.append(finding(
            "strength", f"{pct:.0f}%", f"of final-third possession {where}",
            f"{_frames(sum(p['attack_side'].values()))} in the final third", p["attack_side"][side],
            tags=[f"attack_{side}"],
            action="Keep the midfield and center backs tight and force them wide." if side == "center" else
                   f"Shift our block toward that side: our {OPPOSITE[side]} back and "
                   f"{OPPOSITE[side]}-sided midfielder defend it together."))

    goals = p["goals_for"]
    group, n = _main_position_group(goals)
    if len(goals) >= 2 and n / len(goals) >= 0.5:
        out.append(finding(
            "strength", f"{n} of {len(goals)}", f"goals scored by {group.lower()}s", "goals in the analyzed film", n,
            items=[g for g in goals if _group(g.get("position")) == group],
            tags=[f"scorer_{group.lower()}"],
            action=f"Keep tight marking on their {group.lower()}s in and around the box."))

    shots_90 = per90(p, len(p["shots_for"]))
    if p["minutes_covered"] >= 20 and shots_90 >= 12:
        out.append(finding(
            "strength", f"{shots_90:.1f}", "shots per 90",
            f"{len(p['shots_for'])} shots in {p['minutes_covered']:.0f} min", len(p["shots_for"]),
            items=p["shots_for"], tags=["shooting"],
            action="Protect the area in front of our box and block shots."))

    crosses = events_of(p["events_for"], "cross")
    if len(crosses) >= 5:
        out.append(finding(
            "strength", f"{len(crosses)}", "crosses", f"{per90(p, len(crosses)):.1f} per 90",
            len(crosses), items=crosses, tags=["crosses"],
            action="Double up on their wide players and cover the far post."))

    counter_shots = _with_build_up(p["shots_for"], "counter")
    counters = counter_shots + events_of(p["events_for"], "counter")
    if len(counters) >= 2:
        out.append(finding(
            "strength", f"{len(counters)}", "counter-attacks",
            f"{len(counter_shots)} ended in a shot", len(counters), items=counters, tags=["counter"],
            action="Keep 2-3 players behind the ball when we attack."))

    presses = events_of(p["events_for"], "press")
    if len(presses) >= 5 and share(p["block_out"], "high") >= 35:
        out.append(finding(
            "strength", f"{len(presses)}", "presses",
            f"{share(p['block_out'], 'high'):.0f}% of defending time in a high block", len(presses),
            items=presses, tags=["press"],
            action="Move the ball quickly past their first line or go long behind it."))

    set_pieces = _with_build_up(p["shots_for"], "set_piece")
    if len(set_pieces) >= 2 or any(s.get("outcome") == "goal" for s in set_pieces):
        goals_sp = sum(s.get("outcome") == "goal" for s in set_pieces)
        out.append(finding(
            "strength", f"{len(set_pieces)}", _say(len(set_pieces), "shot from a set piece", "shots from set pieces"),
            f"{goals_sp} scored",
            len(set_pieces), items=set_pieces, tags=["set_piece"],
            action="Mark their tallest players tightly at corners and free kicks."))

    long_balls = events_of(p["events_for"], "long_ball")
    if len(long_balls) >= 5:
        out.append(finding(
            "strength", f"{len(long_balls)}", "long balls", f"{per90(p, len(long_balls)):.1f} per 90",
            len(long_balls), items=long_balls, tags=["long_ball"],
            action="Win the first header and collect the second ball."))

    against_90 = per90(p, len(p["shots_against"]))
    if p["minutes_covered"] >= 20 and against_90 <= 6:
        out.append(finding(
            "strength", f"{against_90:.1f}", "shots conceded per 90",
            f"{len(p['shots_against'])} in {p['minutes_covered']:.0f} min", max(1, len(p["shots_against"])),
            items=p["shots_against"], tags=["solid_defense"],
            action="Be patient; switch play and shoot from the edge of the box."))

    late = _late(p["goals_for"])
    if len(late) >= 2:
        out.append(finding(
            "strength", f"{len(late)}", "goals in the last 15 minutes", f"of {len(p['goals_for'])} goals",
            len(late), items=late, tags=["late_goals"],
            action="Make defensive changes early and keep our shape late."))

    number, n, pct = _key_player(p["players"])
    if number:
        out.append(finding(
            "strength", f"#{number}", "seen near the ball most", f"{pct:.0f}% of readable numbers",
            n, tags=["key_player"],
            action=f"Know where #{number} is and get tight when they receive it."))
    return out


# ---------- weaknesses ----------

def weaknesses(p):
    out = []
    own_half = [t for t in p["turnovers"] if t.get("zone") and t["zone"][0] <= 3]
    if len(own_half) >= 2:
        side = _most_common_side(own_half)
        where = "mostly central" if side == "center" else f"mostly on their {side}"
        out.append(finding(
            "weakness", f"{len(own_half)}", "turnovers in their own half", where, len(own_half),
            items=own_half, tags=["press", f"press_{OPPOSITE[side]}"],
            action="Press their build-up hard; a turnover there is close to their goal."))

    side, pct = _main_side(p["defend_side"])
    if side and side != "center" and pct >= 45 and p["defend_side"][side] >= 5:
        out.append(finding(
            "weakness", f"{pct:.0f}%", f"of opponents' attacks come down their {side}",
            f"{_frames(sum(p['defend_side'].values()))} in their defensive third", p["defend_side"][side],
            tags=[f"attack_{OPPOSITE[side]}"],
            action=f"Attack down our {OPPOSITE[side]}: that is their {side} side."))

    against_90 = per90(p, len(p["shots_against"]))
    if p["minutes_covered"] >= 20 and against_90 >= 12:
        out.append(finding(
            "weakness", f"{against_90:.1f}", "shots conceded per 90",
            f"{len(p['shots_against'])} in {p['minutes_covered']:.0f} min", len(p["shots_against"]),
            items=p["shots_against"], tags=["shooting"],
            action="Shoot early and often."))

    sp_against = _with_build_up(p["shots_against"], "set_piece")
    if sp_against:
        goals = sum(s.get("outcome") == "goal" for s in sp_against)
        out.append(finding(
            "weakness", f"{len(sp_against)}", _say(len(sp_against), "set-piece shot conceded", "set-piece shots conceded"),
            f"{goals} goal{'s' if goals != 1 else ''} conceded", len(sp_against),
            items=sp_against, tags=["set_piece"],
            action="Win corners and free kicks near their box."))

    counter_against = _with_build_up(p["shots_against"], "counter")
    if counter_against:
        goals = sum(s.get("outcome") == "goal" for s in counter_against)
        out.append(finding(
            "weakness", f"{len(counter_against)}",
            _say(len(counter_against), "shot conceded on the counter", "shots conceded on the counter"),
            f"{goals} goal{'s' if goals != 1 else ''} conceded", len(counter_against),
            items=counter_against, tags=["counter"],
            action="Stay compact, let them commit forward, then break fast."))

    defending = sum(v for k, v in p["block_out"].items() if k)
    high = share(p["block_out"], "high")
    if high >= 40:
        out.append(finding(
            "weakness", f"{high:.0f}%", "of defending time in a high block",
            f"{_frames(defending)} without the ball", p["block_out"]["high"], tags=["long_ball", "counter"],
            action="Play balls in behind their defense."))

    low = share(p["block_out"], "low")
    if low >= 50:
        out.append(finding(
            "weakness", f"{low:.0f}%", "of defending time in a low block",
            f"{_frames(defending)} without the ball", p["block_out"]["low"], tags=["possession", "shooting"],
            action="Be patient, switch play and shoot from the edge of the box."))

    poss = p["possession_pct"]
    if poss is not None and poss <= 42:
        out.append(finding(
            "weakness", f"{poss:.0f}%", "possession", f"from {_frames(_poss_frames(p))}",
            p["possession"]["other_team"], tags=["press", "possession"],
            action="Press them early."))

    shots_90 = per90(p, len(p["shots_for"]))
    if p["minutes_covered"] >= 20 and shots_90 <= 6:
        out.append(finding(
            "weakness", f"{shots_90:.1f}", "shots per 90",
            f"{len(p['shots_for'])} in {p['minutes_covered']:.0f} min", max(1, len(p["shots_for"])),
            items=p["shots_for"], tags=["few_chances"],
            action="Stay organized and don't over-commit."))

    late = _late(p["goals_against"])
    if len(late) >= 2:
        out.append(finding(
            "weakness", f"{len(late)}", "goals conceded in the last 15 minutes",
            f"of {len(p['goals_against'])} conceded", len(late), items=late, tags=["late_goals"],
            action="Keep the pressure on in the last 20 minutes."))
    return out


# ---------- context ----------

def context_notes(p):
    """Short notes on game context that change how much the numbers mean."""
    notes = []
    for g in p["games"]:
        vs = g.get("other_team_name") or "opponent"
        strength = g.get("opponent_strength")
        if strength == "weaker":
            notes.append(f"vs {vs}: weaker opponent, attacking numbers may run high")
        elif strength == "stronger":
            notes.append(f"vs {vs}: stronger opponent, defensive numbers may run high")
        if g.get("playoff"):
            notes.append(f"vs {vs}: playoff game")
        if g.get("final_score"):
            notes.append(f"vs {vs}: finished {g['final_score']}")
    if p["minutes_covered"] < 45:
        notes.append(f"Only {p['minutes_covered']:.0f} min analyzed so far, so this is an early read")
    if p["avg_confidence"] and p["avg_confidence"] < 0.5:
        notes.append(f"Film was hard to read (confidence {p['avg_confidence']:.2f})")
    return notes


def setup(p):
    """The team's usual setup as (label, value) facts."""
    side, pct = _main_side(p["attack_side"])
    return [("Shape without the ball", p["formation_out"] or "not clear"),
            ("Defensive block", p["block_out_main"].capitalize() if p["block_out_main"] else "not clear"),
            ("Shape with the ball", p["formation_in"] or "not clear"),
            ("Main attacking side", f"{side.capitalize()} ({pct:.0f}%)" if side else "not clear"),
            ("Possession", f"{p['possession_pct']:.0f}%" if p["possession_pct"] is not None else "not logged")]


def set_piece_numbers(p):
    """Corners and set-piece shots for and against."""
    return {"Corners": len(events_of(p["events_for"], "set_piece", subtype="corner")),
            "Set-piece shots": len(_with_build_up(p["shots_for"], "set_piece")),
            "Set-piece shots conceded": len(_with_build_up(p["shots_against"], "set_piece"))}


# ---------- the matchup ----------

def game_plan(us, them):
    """Line their strengths and weaknesses up against ours (tags that match)."""
    our_s, our_w = strengths(us), weaknesses(us)
    their_s, their_w = strengths(them), weaknesses(them)
    plan = {
        "exploit": [_match(w, our_s) for w in their_w],     # their weakness + our strength
        "counter": [_match(s, our_w) for s in their_s],     # their strength + our weakness
        "fix": [w for w in our_w if any(set(w["tags"]) & set(s["tags"]) for s in their_s)],
        "set_pieces": _set_piece_notes(us, them),
        "first_15": _first_15(them, their_s, their_w),
        "context": context_notes(them),
    }
    plan["exploit"].sort(key=lambda m: -len(m["matches"]))
    plan["counter"].sort(key=lambda m: -len(m["matches"]))
    return plan


def _match(item, candidates):
    """Pair a finding with any of the other team's findings that share a tag."""
    found = [c for c in candidates if set(c["tags"]) & set(item["tags"])]
    return {"item": item, "matches": [c["title"] for c in found], "match_items": found}


def _set_piece_notes(us, them):
    notes = []
    for p, label in ((them, "They"), (us, "We")):
        n = set_piece_numbers(p)
        notes.append(f"{label} ({p['team']}): {n['Corners']} corners logged, "
                     f"{n['Set-piece shots']} shots from set pieces, "
                     f"{n['Set-piece shots conceded']} set-piece shots conceded.")
    return notes


def _first_15(them, their_s, their_w):
    """What to check early in the game to confirm or update the plan."""
    checks = []
    if them["formation_out"]:
        block = them["block_out_main"]
        checks.append(f"Are they defending in a {them['formation_out']}"
                      + (f" {block} block" if block else "") + "?")
    if them["formation_in"]:
        checks.append(f"Do they build up in a {them['formation_in']}?")
    for s in their_s[:3]:
        checks.append(f"Is this still true: {s['title']}?")
    return checks


# ---------- small helpers ----------

def _poss_frames(p):
    return p["possession"]["analyzed_team"] + p["possession"]["other_team"]


def _main_side(counter):
    total = sum(counter.values())
    if not total:
        return None, 0
    side, n = counter.most_common(1)[0]
    return side, 100 * n / total


def _most_common_side(events):
    sides = {"left": 0, "center": 0, "right": 0}
    for e in events:
        y = e["zone"][1]
        sides["left" if y == 1 else "right" if y == 4 else "center"] += 1
    return max(sides, key=sides.get)


def _with_build_up(shots, build_up):
    return [s for s in shots if s.get("build_up") == build_up]


def _late(goals):
    # "late" is set per game in aggregate.py (the last 15 minutes of 80 or 90).
    return [g for g in goals if g.get("late")]


def _key_player(players):
    """The jersey number seen most, if it stands out: (number, frames, % of readable)."""
    total = sum(players.values())
    if not total:
        return None, 0, 0
    number, n = players.most_common(1)[0]
    pct = 100 * n / total
    return (number, n, pct) if n >= 8 and pct >= 25 else (None, 0, 0)


def _group(position):
    g = position_group(position)
    return POSITION_GROUPS[g][0] if g else None


def _main_position_group(goals):
    counts = {}
    for g in goals:
        group = _group(g.get("position"))
        if group:
            counts[group] = counts.get(group, 0) + 1
    if not counts:
        return None, 0
    best = max(counts, key=counts.get)
    return best, counts[best]
