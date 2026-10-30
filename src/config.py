"""Loads games.yaml and handles video times.

Every other module gets game info through here, so the yaml format only
has to be understood in one place.
"""
import os
import sys
from pathlib import Path

import yaml

# True in the website demo, where the app runs inside the browser (Pyodide):
# no ffmpeg, no threads and no API calls, so it only shows the demo data.
IN_BROWSER = sys.platform == "emscripten"

ROOT = Path(__file__).resolve().parent.parent
FILM_DIR = ROOT / "film"
FRAMES_DIR = ROOT / "frames"
LOGS_DIR = ROOT / "logs"
REPORTS_DIR = ROOT / "reports"
GAMES_FILE = ROOT / "games.yaml"
ENV_FILE = ROOT / ".env"

SAMPLE_DIR = ROOT / "sample"
SAMPLE_GAMES_FILE = SAMPLE_DIR / "games.yaml"
SAMPLE_LOGS_DIR = SAMPLE_DIR / "logs"
SAMPLE_REPORTS_DIR = SAMPLE_DIR / "reports"

DEFAULT_HALF_LENGTH = 45     # minutes; high school games are usually 40
LATE_MINUTES = 15            # goals in the last 15 minutes of a game count as "late"

TEAMS = ("analyzed_team", "other_team")
STRENGTHS = ("weaker", "similar", "stronger")
DIRECTIONS = ("left", "right")
CAMERAS = ("follow", "broadcast", "fixed")   # follow = an automatic camera that tracks the ball


def project_path(path):
    """A path from a manifest (stored relative to the project folder) as a full path."""
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def _number(value):
    """A number from yaml or a form (int, float or numeric text), else None."""
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def parse_time(value):
    """Turn "mm:ss" or "h:mm:ss" (or a number of seconds) into seconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        parts = [float(p) for p in str(value).strip().split(":")]
    except ValueError:
        raise ValueError(f"Can't read the time '{value}'. Use mm:ss or h:mm:ss, like 23:10.") from None
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def format_time(seconds):
    """Turn seconds into "mm:ss" (minutes can go past 59, like a video player)."""
    seconds = int(round(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def load_config(path=None):
    """Read games.yaml and return {"matchup": {...}, "games": [...]}."""
    data = load_raw(path)
    games = [_prepare_game(g) for g in data.get("games") or []]
    return {"matchup": data.get("matchup") or {}, "games": games}


def load_raw(path=None):
    """games.yaml exactly as written (no computed fields). {} if it doesn't exist."""
    path = Path(path or GAMES_FILE)
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def save_raw(data, path=None):
    """Write games.yaml (used by the app's game form). Comments are not kept."""
    header = ("# Sportive Scout game info (saved by the app; you can also edit it by hand).\n"
              "# Times are VIDEO times, as shown in your video player (\"mm:ss\" or \"h:mm:ss\").\n\n")
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
    Path(path or GAMES_FILE).write_text(header + text)


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
    game["goal_times"] = [dict(g) for g in game.get("goal_times") or []]
    game.setdefault("opponent_strength", "similar")
    game.setdefault("playoff", False)
    game.setdefault("notes", "")
    game["half_length"] = _number(game.get("half_length")) or DEFAULT_HALF_LENGTH
    game["kickoff_s"] = parse_time(game.get("kickoff_time")) or 0.0
    game["first_half_end_s"] = parse_time(game.get("first_half_end"))
    game["second_half_start_s"] = parse_time(game.get("second_half_start"))
    for goal in game["goal_times"]:
        goal["seconds"] = parse_time(goal.get("time"))
    return game


def validate_config(cfg):
    """Plain-language problems with games.yaml. An empty list means all good."""
    problems = []
    m = cfg["matchup"]
    teams = {m.get("our_team"), m.get("opponent")} - {None, ""}
    if len(teams) < 2:
        problems.append("matchup needs two different team names: our_team and opponent.")
    ids = [g.get("id") for g in cfg["games"]]
    for dup in sorted({i for i in ids if i and ids.count(i) > 1}):
        problems.append(f"The game id '{dup}' is used more than once.")
    for g in cfg["games"]:
        problems += [f"{g.get('id') or '(game without an id)'}: {p}" for p in _game_problems(g, m)]
    return problems


def _game_problems(g, matchup):
    """Problems with one prepared game entry."""
    out = []
    if not g.get("id"):
        out.append("needs an id (a short name with no spaces).")
    elif " " in str(g["id"]):
        out.append("the id can't contain spaces.")
    if not g.get("file"):
        out.append("file is empty (the video's name inside film/).")
    name = g.get("analyzed_team_name")
    if name not in (matchup.get("our_team"), matchup.get("opponent")):
        out.append(f"analyzed_team_name '{name}' must match our_team or opponent in matchup.")
    expected = {"us": matchup.get("our_team"), "opponent": matchup.get("opponent")}.get(g.get("team_analyzed"))
    if expected and name and name != expected:
        out.append(f"team_analyzed says '{g.get('team_analyzed')}' but analyzed_team_name is '{name}'.")
    if g.get("attacking_direction", "right") not in DIRECTIONS:
        out.append("attacking_direction must be left or right.")
    if g.get("opponent_strength") not in STRENGTHS:
        out.append("opponent_strength must be weaker, similar or stronger.")
    if g.get("detail") not in (None, "", "standard", "high"):
        out.append("detail must be standard or high.")
    if g.get("camera") not in (None, "", *CAMERAS):
        out.append("camera must be follow, broadcast or fixed (or left empty).")
    if not 10 <= g.get("half_length", DEFAULT_HALF_LENGTH) <= 60:
        out.append("half_length must be the minutes in one half, like 45 (or 40 for high school).")
    kickoff, end, second = g["kickoff_s"], g["first_half_end_s"], g["second_half_start_s"]
    if second is not None and second <= kickoff:
        out.append("second_half_start must be after kickoff_time.")
    if end is not None and end <= kickoff:
        out.append("first_half_end must be after kickoff_time.")
    if end is not None and second is not None and end > second:
        out.append("first_half_end must be before second_half_start.")
    for goal in g["goal_times"]:
        if goal.get("seconds") is None:
            out.append("a goal in goal_times has no time.")
        if goal.get("team", "analyzed_team") not in TEAMS:
            out.append(f"goal at {goal.get('time')}: team must be analyzed_team or other_team.")
    return out


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


def game_minute(game, video_s, half=None):
    """Game clock minute for a video time. The 2nd half starts at the half length (45' or 40').

    `half` can be passed when it is already known (a logged frame keeps its half).
    """
    half = half_for(game, video_s) if half is None else half
    if half == 2:
        return game.get("half_length", DEFAULT_HALF_LENGTH) + (video_s - game["second_half_start_s"]) / 60
    return max(0.0, (video_s - game["kickoff_s"]) / 60)


def is_late(game, minute):
    """True for a game minute in the last LATE_MINUTES of regulation time."""
    length = 2 * game.get("half_length", DEFAULT_HALF_LENGTH)
    return minute is not None and minute >= length - LATE_MINUTES


def attacking_direction(game, half):
    """Which screen side the analyzed team attacks in a given half."""
    first = game.get("attacking_direction", "right")
    if half == 2:
        return "left" if first == "right" else "right"
    return first


def load_env(path=None):
    """Copy KEY=value lines from .env into the environment (never overwrites).

    Lets the Claude API key live in a git-ignored file instead of the shell.
    """
    path = Path(path or ENV_FILE)
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        os.environ.setdefault(key, value.strip().strip("\"'"))
