"""Loads games.yaml and handles video times.

Every other module gets game info through here, so the yaml format only
has to be understood in one place.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FILM_DIR = ROOT / "film"
FRAMES_DIR = ROOT / "frames"
LOGS_DIR = ROOT / "logs"
REPORTS_DIR = ROOT / "reports"
GAMES_FILE = ROOT / "games.yaml"

SAMPLE_DIR = ROOT / "sample"
SAMPLE_GAMES_FILE = SAMPLE_DIR / "games.yaml"
SAMPLE_LOGS_DIR = SAMPLE_DIR / "logs"
SAMPLE_REPORTS_DIR = SAMPLE_DIR / "reports"


def parse_time(value):
    """Turn "mm:ss" or "h:mm:ss" (or a number of seconds) into seconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    parts = [float(p) for p in str(value).strip().split(":")]
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def format_time(seconds):
    """Turn seconds into "mm:ss" (minutes can go past 59, like a video player)."""
    seconds = int(round(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def load_config(path=GAMES_FILE):
    """Read games.yaml and return {"matchup": {...}, "games": [...]}."""
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    games = [_prepare_game(g) for g in data.get("games") or []]
    return {"matchup": data.get("matchup") or {}, "games": games}


def get_game(config, game_id):
    """Find one game by its id, or stop with a clear message."""
    for game in config["games"]:
        if game["id"] == game_id:
            return game
    ids = ", ".join(g["id"] for g in config["games"]) or "(none)"
    raise SystemExit(f"No game with id '{game_id}' in games.yaml. Known ids: {ids}")


def _prepare_game(game):
    """Fill defaults and pre-compute the times in seconds."""
    game = dict(game)
    game["kit_colors"] = game.get("kit_colors") or {}
    game["goal_times"] = game.get("goal_times") or []
    game.setdefault("opponent_strength", "similar")
    game.setdefault("playoff", False)
    game.setdefault("notes", "")
    game["kickoff_s"] = parse_time(game.get("kickoff_time")) or 0.0
    game["first_half_end_s"] = parse_time(game.get("first_half_end"))
    game["second_half_start_s"] = parse_time(game.get("second_half_start"))
    for goal in game["goal_times"]:
        goal["seconds"] = parse_time(goal.get("time"))
    return game


def half_for(game, video_s):
    """Which half a video time is in: 1, 2, or 0 for break / before kickoff."""
    if video_s < game["kickoff_s"]:
        return 0
    second = game["second_half_start_s"]
    if second is not None and video_s >= second:
        return 2
    end = game["first_half_end_s"]
    if end is not None and video_s > end:
        return 0
    return 1


def game_minute(game, video_s):
    """Game clock minute for a video time (2nd half starts at 45')."""
    half = half_for(game, video_s)
    if half == 2:
        return 45 + (video_s - game["second_half_start_s"]) / 60
    return max(0.0, (video_s - game["kickoff_s"]) / 60)


def attacking_direction(game, half):
    """Which screen side the analyzed team attacks in a given half."""
    first = game.get("attacking_direction", "right")
    if half == 2:
        return "left" if first == "right" else "right"
    return first
