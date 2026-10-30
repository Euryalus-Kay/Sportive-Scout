"""Generates FAKE moment logs for the demo games in sample/games.yaml.

Each fake team has a "personality" (where it attacks, how it defends, ...)
so the stats, insights and game plan have real patterns to find. Output is
the same format analyzer.py stores, so the rest of the app can't tell the
difference. Nothing here is real data.
"""
import json
import random

from src import config

FRAME_STEP = 4
HALF_FRAMES = 45 * 60 // FRAME_STEP

PERSONALITIES = {
    "sample_riverside_vs_lakeview": {
        "possession": 0.58,
        "attack_rows": [0.15, 0.2, 0.2, 0.45],      # their left -> right, final third
        "defend_rows": [0.3, 0.2, 0.2, 0.3],
        "shape_in": "4-3-3", "shape_out": "4-4-2", "other_shape": "4-4-2",
        "block_out": {"high": 0.5, "mid": 0.35, "low": 0.15},
        "press": 0.10, "cross": 0.05, "long_ball": 0.02, "shot": 0.035,
        "turnover_own_half": 0.02, "turnover_rows": [0.25, 0.25, 0.25, 0.25],
        "counter_against": 0.4, "set_piece_against": 0.1,
        "shooters": ["ST", "ST", "RW", "LW", "CM", "AM"],
        "build_ups": ["wide", "wide", "central", "press", "set_piece"],
        "numbers": ["9", "7", "10", "8", "11", "4", "5"],
    },
    "sample_northgate_vs_hillcrest": {
        "possession": 0.46,
        "attack_rows": [0.55, 0.15, 0.15, 0.15],
        "defend_rows": [0.55, 0.15, 0.15, 0.15],
        "shape_in": "4-2-3-1", "shape_out": "4-5-1", "other_shape": "4-3-3",
        "block_out": {"high": 0.1, "mid": 0.3, "low": 0.6},
        "press": 0.02, "cross": 0.12, "long_ball": 0.05, "shot": 0.03,
        "turnover_own_half": 0.05, "turnover_rows": [0.1, 0.15, 0.15, 0.6],
        "counter_against": 0.1, "set_piece_against": 0.4,
        "shooters": ["ST", "LW", "LW", "AM", "RW", "DM"],
        "build_ups": ["wide", "wide", "counter", "counter", "long_ball"],
        "numbers": ["11", "9", "10", "14", "6", "3", "2"],
    },
}


def ensure(force=False):
    """Create the fake logs if they don't exist yet."""
    cfg = config.load_config(config.SAMPLE_GAMES_FILE)
    config.SAMPLE_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    for game in cfg["games"]:
        path = config.SAMPLE_LOGS_DIR / f"{game['id']}.json"
        if force or not path.exists():
            path.write_text(json.dumps(generate(game), indent=1))


def generate(game):
    rng = random.Random(game["id"])
    traits = PERSONALITIES[game["id"]]
    goals = {_snap(game, g["seconds"]): g for g in game["goal_times"]}
    log, has_ball = [], rng.random() < traits["possession"]
    for start in (game["kickoff_s"], game["second_half_start_s"]):
        for i in range(HALF_FRAMES):
            t = start + i * FRAME_STEP
            # possession changes now and then, leaning toward the team's share
            if rng.random() < 0.12:
                has_ball = rng.random() < traits["possession"]
            log.append(_frame(game, traits, rng, t, has_ball, goals.get(t)))
    return log


def _snap(game, seconds):
    """Round a goal time to the nearest generated frame."""
    start = game["second_half_start_s"] if seconds >= game["second_half_start_s"] else game["kickoff_s"]
    return start + round((seconds - start) / FRAME_STEP) * FRAME_STEP


def _frame(game, traits, rng, t, has_ball, goal):
    view = rng.choices(["wide", "close", "replay"], [0.88, 0.08, 0.04])[0]
    possession = "analyzed_team" if has_ball else "other_team"
    roll = rng.random()
    if roll < 0.05:
        possession = "dead_ball"
    elif roll < 0.10:
        possession = "contested"
    zone = _zone(traits, rng, has_ball)
    events = [] if view != "wide" else _events(traits, rng, has_ball, zone, possession)
    if goal:
        view, possession = "wide", goal["team"]
        zone = [6, rng.choice([2, 3])] if goal["team"] == "analyzed_team" else [1, rng.choice([2, 3])]
        events = [{"type": "shot", "team": goal["team"], "outcome": "goal",
                   "position": goal.get("position"), "build_up": goal.get("how")}]
    for e in events:
        if e["type"] == "shot":
            e["xy"] = _shot_xy(rng, e["team"])
    block = rng.choices(list(traits["block_out"]), list(traits["block_out"].values()))[0]
    return {
        "timestamp": config.format_time(t),
        "video_seconds": t,
        "half": config.half_for(game, t),
        "game_minute": round(config.game_minute(game, t), 1),
        "source": "pass1", "batch": 0, "view": view, "possession": possession,
        "ball_zone": zone, "ball_xy": None,
        "analyzed_team_shape": traits["shape_in"] if has_ball else traits["shape_out"],
        "analyzed_team_block": None if has_ball else block,
        "other_team_shape": traits["other_shape"],
        "other_team_block": "mid",
        "events": events,
        "players": rng.sample(traits["numbers"], rng.choice([0, 0, 1, 2])),
        "confidence": round(rng.uniform(0.45, 0.85), 2),
        "note": "fake demo frame",
    }


def _zone(traits, rng, has_ball):
    if has_ball:
        x = rng.choices(range(1, 7), [0.06, 0.12, 0.2, 0.24, 0.22, 0.16])[0]
        rows = traits["attack_rows"] if x >= 5 else [0.25] * 4
    else:
        x = rng.choices(range(1, 7), [0.18, 0.24, 0.22, 0.16, 0.12, 0.08])[0]
        rows = traits["defend_rows"] if x <= 2 else [0.25] * 4
    return [x, rng.choices(range(1, 5), rows)[0]]


def _events(traits, rng, has_ball, zone, possession):
    x, y = zone
    events = []
    if possession == "dead_ball" and rng.random() < 0.3:
        events.append({"type": "set_piece", "team": rng.choice(["analyzed_team", "other_team"]),
                       "subtype": rng.choice(["corner", "free_kick", "throw_in"])})
    if has_ball:
        if x >= 5 and rng.random() < traits["shot"]:
            events.append({"type": "shot", "team": "analyzed_team",
                           "outcome": rng.choices(["on_target", "off_target", "blocked"], [0.4, 0.4, 0.2])[0],
                           "position": rng.choice(traits["shooters"]),
                           "build_up": rng.choice(traits["build_ups"])})
        if x >= 4 and y in (1, 4) and rng.random() < traits["cross"]:
            events.append({"type": "cross", "team": "analyzed_team"})
        if x <= 3 and rng.random() < traits["long_ball"]:
            events.append({"type": "long_ball", "team": "analyzed_team"})
        if x <= 3 and rng.random() < traits["turnover_own_half"]:
            zone[1] = rng.choices(range(1, 5), traits["turnover_rows"])[0]
            events.append({"type": "turnover", "team": "analyzed_team"})
    else:
        if x >= 4 and rng.random() < traits["press"]:
            events.append({"type": "press", "team": "analyzed_team"})
        if x <= 2 and rng.random() < 0.03:
            build = "counter" if rng.random() < traits["counter_against"] else (
                "set_piece" if rng.random() < traits["set_piece_against"] else "central")
            events.append({"type": "shot", "team": "other_team",
                           "outcome": rng.choices(["on_target", "off_target", "blocked"], [0.4, 0.4, 0.2])[0],
                           "position": rng.choice(["ST", "LW", "RW", "CM"]), "build_up": build})
    return events


def _shot_xy(rng, team):
    """A believable shot spot: inside/near the box at the right end."""
    x, y = rng.uniform(78, 96), rng.gauss(50, 14)
    if team == "other_team":
        x = 100 - x
    return [round(x, 1), round(max(5, min(95, y)), 1)]


if __name__ == "__main__":
    ensure(force=True)
    print(f"Fake demo logs written to {config.SAMPLE_LOGS_DIR.relative_to(config.ROOT)}/")
