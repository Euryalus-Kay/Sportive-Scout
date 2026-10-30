"""Strengths, weaknesses, counters and the matchup game plan.

Each finding comes from a simple rule over a team profile (see aggregate.py),
with the count and timestamps that back it up. Findings carry `tags`, always
written from the ATTACKING team's point of view (e.g. "attack_left" means
"attacks get through down the attacker's left"). That lets an opponent
weakness be matched to one of our strengths with the same tag.
"""
from src.aggregate import events_of, share
from src.visualize import POSITION_GROUPS, position_group

STRONG, POSSIBLE, ONCE = "strong pattern", "possible pattern", "seen once"
OPPOSITE = {"left": "right", "right": "left", "center": "center"}


def evidence_label(count):
    """Strong pattern (5+), possible pattern (2-4) or seen once."""
    if count >= 5:
        return STRONG
    if count >= 2:
        return POSSIBLE
    return ONCE


def finding(kind, title, detail, count, items=(), tags=(), action=""):
    """One strength or weakness. `action` = how to counter it / how to exploit it."""
    stamps = [f"{e['timestamp']}" for e in items if e.get("timestamp")]
    return {"kind": kind, "title": title, "detail": detail, "count": count,
            "evidence": evidence_label(count), "timestamps": stamps[:12],
            "tags": list(tags), "action": action}


def per90(p, n):
    return n * p["per90"]


# ---------- strengths ----------

def strengths(p):
    out = []
    poss = p["possession_pct"]
    if poss is not None and poss >= 55:
        out.append(finding(
            "strength", f"Controls possession ({poss:.0f}%)",
            "They keep the ball for long spells.", p["possession"]["analyzed_team"],
            tags=["possession"],
            action="Stay compact and let them pass in harmless areas; win it in midfield "
                   "and break fast before they can reset."))

    side, pct = _main_side(p["attack_side"])
    if side and pct >= 45 and p["attack_side"][side] >= 5:
        if side == "center":
            out.append(finding(
                "strength", f"Attacks mostly through the middle ({pct:.0f}% of final-third possession)",
                "Final-third possession is concentrated centrally.", p["attack_side"][side],
                tags=["attack_center"],
                action="Keep the midfield and center backs tight together and force them wide, "
                       "where crosses are easier to defend."))
        else:
            out.append(finding(
                "strength", f"Attacks mostly down their {side} ({pct:.0f}% of final-third possession)",
                f"Most of their final-third possession is on their {side} side.",
                p["attack_side"][side], tags=[f"attack_{side}"],
                action=f"Shift our block toward that side: our {OPPOSITE[side]} back and "
                       f"{OPPOSITE[side]}-sided midfielder must defend it together, with a "
                       "central midfielder ready to cover."))

    goals = p["goals_for"]
    group, n = _main_position_group(goals)
    if len(goals) >= 2 and n / len(goals) >= 0.5:
        out.append(finding(
            "strength", f"Most goals come from {group.lower()}s ({n} of {len(goals)})",
            "Their scoring is concentrated in one area of the team.", n,
            items=[g for g in goals if _group(g.get("position")) == group],
            tags=[f"scorer_{group.lower()}"],
            action=f"Keep tight marking on their {group.lower()}s in and around the box; "
                   "don't let them turn or run in behind."))

    shots_90 = per90(p, len(p["shots_for"]))
    if p["minutes_covered"] >= 20 and shots_90 >= 12:
        out.append(finding(
            "strength", f"Creates a lot of shots ({shots_90:.0f} per 90)",
            "They get the ball into shooting areas often.", len(p["shots_for"]),
            items=p["shots_for"], tags=["shooting"],
            action="Protect the area in front of our box: a holding midfielder screens, "
                   "defenders step to block shots."))

    crosses = events_of(p["events_for"], "cross")
    if len(crosses) >= 5:
        out.append(finding(
            "strength", f"Crosses a lot ({len(crosses)} crosses)",
            "Wide delivery is a main way they create chances.", len(crosses),
            items=crosses, tags=["crosses"],
            action="Stop crosses at the source by doubling up on their wide players, and "
                   "always have the far post covered."))

    counters = _with_build_up(p["shots_for"], "counter") + events_of(p["events_for"], "counter")
    if len(counters) >= 2:
        out.append(finding(
            "strength", f"Dangerous on the counter ({len(counters)} counters)",
            "They attack quickly after winning the ball.", len(counters),
            items=counters, tags=["counter"],
            action="When we attack, keep 2-3 players behind the ball (rest defense) and "
                   "foul tactically early in their counter if needed."))

    presses = events_of(p["events_for"], "press")
    if len(presses) >= 5 and share(p["block_out"], "high") >= 35:
        out.append(finding(
            "strength", f"Presses high ({len(presses)} presses)",
            "They try to win the ball back near our goal.", len(presses),
            items=presses, tags=["press"],
            action="Move the ball quickly past their first line, use the goalkeeper as an "
                   "extra passer, and go long into the space behind their press."))

    set_pieces = _with_build_up(p["shots_for"], "set_piece")
    if len(set_pieces) >= 2 or any(s.get("outcome") == "goal" for s in set_pieces):
        out.append(finding(
            "strength", f"Set-piece threat ({len(set_pieces)} shots from set pieces)",
            "Corners and free kicks turn into chances.", len(set_pieces),
            items=set_pieces, tags=["set_piece"],
            action="Mark their tallest players tightly at corners and free kicks, and "
                   "clear the second ball quickly."))

    long_balls = events_of(p["events_for"], "long_ball")
    if len(long_balls) >= 5:
        out.append(finding(
            "strength", f"Play direct ({len(long_balls)} long balls)",
            "They often skip midfield with long passes.", len(long_balls),
            items=long_balls, tags=["long_ball"],
            action="Win the first header, have a midfielder collect the second ball, and "
                   "keep our back line from getting caught too high."))

    against_90 = per90(p, len(p["shots_against"]))
    if p["minutes_covered"] >= 20 and against_90 <= 6:
        out.append(finding(
            "strength", f"Hard to create chances against ({against_90:.0f} shots conceded per 90)",
            "Opponents rarely get shots off.", max(1, len(p["shots_against"])),
            items=p["shots_against"], tags=["solid_defense"],
            action="Be patient; quick switches of play and shots from the edge of the box "
                   "may be the best chances."))
    return out


# ---------- weaknesses ----------

def weaknesses(p):
    out = []
    own_half = [t for t in p["turnovers"] if t.get("zone") and t["zone"][0] <= 3]
    if len(own_half) >= 2:
        side = _most_common_side(own_half)
        if side == "center":
            where, focus = ", mostly centrally", "through the middle"
        else:
            where, focus = f", mostly on their {side} side", f"on their {side} (our {OPPOSITE[side]})"
        out.append(finding(
            "weakness", f"Lose the ball in their own half ({len(own_half)} times){where}",
            "Turnovers close to their own goal.", len(own_half),
            items=own_half, tags=["press", f"press_{OPPOSITE[side]}"],
            action=f"Press their build-up hard, especially {focus}. "
                   "A turnover there is close to their goal."))

    side, pct = _main_side(p["defend_side"])
    if side and side != "center" and pct >= 45 and p["defend_side"][side] >= 5:
        attacker_side = OPPOSITE[side]
        out.append(finding(
            "weakness", f"Opponents get into their box down their {side} ({pct:.0f}%)",
            f"When defending deep, most of the danger comes down their {side} side.",
            p["defend_side"][side], tags=[f"attack_{attacker_side}"],
            action=f"Attack down our {attacker_side}: that is their {side} side, where "
                   "opponents already find space."))

    against_90 = per90(p, len(p["shots_against"]))
    if p["minutes_covered"] >= 20 and against_90 >= 12:
        out.append(finding(
            "weakness", f"Concede a lot of shots ({against_90:.0f} per 90)",
            "Opponents get into shooting positions often.", len(p["shots_against"]),
            items=p["shots_against"], tags=["shooting"],
            action="Shoot early and often; get bodies into the box for rebounds."))

    sp_against = _with_build_up(p["shots_against"], "set_piece")
    if sp_against:
        goals = sum(s.get("outcome") == "goal" for s in sp_against)
        out.append(finding(
            "weakness", f"Vulnerable at set pieces ({len(sp_against)} shots, {goals} goals conceded)",
            "Corners and free kicks against them lead to chances.", len(sp_against),
            items=sp_against, tags=["set_piece"],
            action="Win corners and free kicks near their box, and practice our best "
                   "set-piece routines this week."))

    counter_against = _with_build_up(p["shots_against"], "counter")
    if counter_against:
        out.append(finding(
            "weakness", f"Caught on the counter ({_plural(len(counter_against), 'shot')} conceded)",
            "Chances against them come after they lose the ball going forward.",
            len(counter_against), items=counter_against, tags=["counter"],
            action="Stay compact, let them commit players forward, then break fast."))

    high = share(p["block_out"], "high")
    if high >= 40:
        out.append(finding(
            "weakness", f"High defensive line leaves space behind ({high:.0f}% of defending frames)",
            "They defend far up the field.", p["block_out"]["high"],
            tags=["long_ball", "counter"],
            action="Play balls in behind their defense for our fastest forwards; "
                   "beat the first press and the space is there."))

    low = share(p["block_out"], "low")
    if low >= 50:
        out.append(finding(
            "weakness", f"Sit deep without the ball ({low:.0f}% of defending frames)",
            "They give up space in front of their defense.", p["block_out"]["low"],
            tags=["possession", "shooting"],
            action="Be patient with the ball, switch play to stretch them, and shoot "
                   "from the edge of the box."))

    poss = p["possession_pct"]
    if poss is not None and poss <= 42:
        out.append(finding(
            "weakness", f"Struggle to keep the ball ({poss:.0f}% possession)",
            "They spend long spells without the ball.", p["possession"]["other_team"],
            tags=["press", "possession"],
            action="Press them early; they are not comfortable keeping the ball."))

    shots_90 = per90(p, len(p["shots_for"]))
    if p["minutes_covered"] >= 20 and shots_90 <= 6:
        out.append(finding(
            "weakness", f"Create few chances ({shots_90:.0f} shots per 90)",
            "They struggle to get shots off.", max(1, len(p["shots_for"])),
            items=p["shots_for"], tags=["few_chances"],
            action="Stay organized and don't over-commit; they rely on mistakes to score."))
    return out


# ---------- context ----------

def context_notes(p):
    """Warnings about game context that change how much the numbers mean."""
    notes = []
    for g in p["games"]:
        vs = g.get("other_team_name") or "opponent"
        strength = g.get("opponent_strength")
        if strength == "weaker":
            notes.append(f"vs {vs}: opponent was weaker, so attacking numbers may look better than usual.")
        elif strength == "stronger":
            notes.append(f"vs {vs}: opponent was stronger, so defensive numbers may look worse than usual.")
        if g.get("playoff"):
            notes.append(f"vs {vs}: playoff game, so expect a similar high-stakes approach.")
        if g.get("final_score"):
            notes.append(f"vs {vs}: final score {g['final_score']} (game state affects tactics).")
    if p["minutes_covered"] < 45:
        notes.append(f"Only {p['minutes_covered']:.0f} minutes analyzed so far; treat patterns as early reads.")
    if p["avg_confidence"] and p["avg_confidence"] < 0.5:
        notes.append(f"Average confidence is low ({p['avg_confidence']:.2f}); the film was hard to read.")
    return notes


# ---------- the matchup ----------

def game_plan(us, them):
    """Match their strengths/weaknesses against ours."""
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
    matches = [c["title"] for c in candidates if set(c["tags"]) & set(item["tags"])]
    return {"item": item, "matches": matches}


def _set_piece_notes(us, them):
    notes = []
    for p, label in ((them, "They"), (us, "We")):
        sp_for = _with_build_up(p["shots_for"], "set_piece")
        sp_against = _with_build_up(p["shots_against"], "set_piece")
        corners = events_of(p["events_for"], "set_piece", subtype="corner")
        notes.append(f"{label} ({p['team']}): {len(corners)} corners logged, "
                     f"{len(sp_for)} shots from set pieces, "
                     f"{len(sp_against)} set-piece shots conceded.")
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
        checks.append(f"Is this still true: {s['title'].split(' (')[0].lower()}?")
    for w in their_w[:2]:
        checks.append(f"Test early: {w['action'].split('.')[0].lower()}.")
    return checks


# ---------- small helpers ----------

def _plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


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
