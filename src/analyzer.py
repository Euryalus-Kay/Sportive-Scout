"""Analysis interface: turns grid images into moment log entries.

Right now the "analyzer" is Claude Code itself: it looks at a batch of grids,
writes what it sees to a JSON file, and `ManualClaudeCodeAnalyzer` reads that
file. Later an `ApiAnalyzer` (Claude Haiku / Sonnet) can implement the same
`analyze_batch` method and nothing else has to change.

What the analyzer writes per frame (screen coordinates, as seen in the image):
    {
      "timestamp": "12:34",                  # from the cell label
      "view": "wide",                        # wide | close | replay | other
      "possession": "analyzed_team",         # analyzed_team | other_team | contested | dead_ball
      "ball_screen": [col, row],             # 6x4 grid on screen: col 1-6 left->right,
                                             #   row 1-4 top (far touchline) -> bottom
      "ball_xy_screen": [x, y],              # optional, 0-100 on screen, for shot spots
      "analyzed_team_shape": "4-3-3",
      "analyzed_team_block": "mid",          # low | mid | high
      "other_team_shape": "4-4-2",
      "other_team_block": "low",
      "events": ["press", {"type": "shot", "team": "analyzed_team",
                           "outcome": "on_target", "position": "ST",
                           "build_up": "wide"}],
      "players": ["10"],
      "confidence": 0.6,
      "note": "..."
    }
The code flips screen positions into "relative to the analyzed team" so that
zone 6 / x=100 is always the end they attack, in both halves.

Usage:
    python -m src.analyzer status --game GAME_ID
    python -m src.analyzer next   --game GAME_ID [--pass 2]
    python -m src.analyzer save   --game GAME_ID --batch 3 --input entries.json [--pass 2]
"""
import argparse
import json
from abc import ABC, abstractmethod

from src import config

VIEWS = {"wide", "close", "replay", "other"}
POSSESSION = {"analyzed_team", "other_team", "contested", "dead_ball"}
BLOCKS = {"low", "mid", "high"}
TEAMS = {"analyzed_team", "other_team"}


# ---------- the interface ----------

class Analyzer(ABC):
    """Anything that can look at one batch of grids and describe each frame."""

    @abstractmethod
    def analyze_batch(self, game, pass_no, batch):
        """Return a list of raw entries (format in the module docstring)."""


class ManualClaudeCodeAnalyzer(Analyzer):
    """Reads entries that Claude Code wrote by hand after viewing the grids."""

    def __init__(self, input_path):
        self.input_path = input_path

    def analyze_batch(self, game, pass_no, batch):
        with open(self.input_path) as f:
            return json.load(f)


# ---------- turning raw entries into log entries ----------

def to_relative_zone(col, row, direction):
    """Screen zone -> zone relative to the analyzed team (6 = their attacking end)."""
    if direction == "right":
        return [col, row]
    return [7 - col, 5 - row]


def to_relative_xy(x, y, direction):
    """Screen 0-100 position -> relative position (x=100 is their attacking goal)."""
    if direction == "right":
        return [x, y]
    return [100 - x, 100 - y]


def normalize_event(event, possession, direction):
    """Events can be plain strings ("press") or dicts; always return a dict."""
    if isinstance(event, str):
        event = {"type": event}
    event = dict(event)
    event["type"] = event["type"].strip().lower()
    if event.get("team") not in TEAMS:
        event["team"] = possession if possession in TEAMS else None
    if event.get("xy_screen"):
        event["xy"] = to_relative_xy(*event.pop("xy_screen"), direction)
    return event


def normalize_entry(raw, game, pass_no, batch_no, cells_by_time):
    """Validate one raw entry and convert it into the stored log format."""
    ts = raw["timestamp"]
    if ts not in cells_by_time:
        raise ValueError(f"timestamp {ts} is not a frame in this batch")
    cell = cells_by_time[ts]
    direction = config.attacking_direction(game, cell["half"] or 1)

    view = raw.get("view", "wide")
    possession = raw.get("possession", "contested")
    if view not in VIEWS:
        raise ValueError(f"{ts}: view must be one of {sorted(VIEWS)}")
    if possession not in POSSESSION:
        raise ValueError(f"{ts}: possession must be one of {sorted(POSSESSION)}")

    zone = None
    if raw.get("ball_screen"):
        col, row = raw["ball_screen"]
        if not (1 <= col <= 6 and 1 <= row <= 4):
            raise ValueError(f"{ts}: ball_screen must be [1-6, 1-4]")
        zone = to_relative_zone(col, row, direction)
    xy = to_relative_xy(*raw["ball_xy_screen"], direction) if raw.get("ball_xy_screen") else None

    return {
        "timestamp": ts,
        "video_seconds": cell["video_seconds"],
        "half": cell["half"],
        "game_minute": cell["game_minute"],
        "source": f"pass{pass_no}",
        "batch": batch_no,
        "view": view,
        "possession": possession,
        "ball_zone": zone,
        "ball_xy": xy,
        "analyzed_team_shape": raw.get("analyzed_team_shape"),
        "analyzed_team_block": _block(raw.get("analyzed_team_block")),
        "other_team_shape": raw.get("other_team_shape"),
        "other_team_block": _block(raw.get("other_team_block")),
        "events": [normalize_event(e, possession, direction) for e in raw.get("events", [])],
        "players": [str(p) for p in raw.get("players", [])],
        "confidence": max(0.0, min(1.0, float(raw.get("confidence", 0.5)))),
        "note": raw.get("note", ""),
    }


def _block(value):
    return value if value in BLOCKS else None


# ---------- files: manifest, log, progress ----------

def load_manifest(game_id, pass_no):
    path = config.FRAMES_DIR / game_id / f"pass{pass_no}" / "manifest.json"
    if not path.exists():
        raise SystemExit(f"No frames yet. Run: python -m src.extract --game {game_id}"
                         + (" --pass 2" if pass_no == 2 else ""))
    return json.loads(path.read_text())


def log_path(game_id, logs_dir=config.LOGS_DIR):
    return logs_dir / f"{game_id}.json"


def progress_path(game_id, logs_dir=config.LOGS_DIR):
    return logs_dir / f"{game_id}_progress.json"


def load_log(game_id, logs_dir=config.LOGS_DIR):
    path = log_path(game_id, logs_dir)
    return json.loads(path.read_text()) if path.exists() else []


def load_progress(game_id, logs_dir=config.LOGS_DIR):
    path = progress_path(game_id, logs_dir)
    return json.loads(path.read_text()) if path.exists() else {}


def save_batch(game, pass_no, batch_no, analyzer):
    """Run the analyzer on one batch, then save the log and progress files."""
    manifest = load_manifest(game["id"], pass_no)
    batch = next((b for b in manifest["batches"] if b["batch"] == batch_no), None)
    if batch is None:
        raise SystemExit(f"Batch {batch_no} does not exist for pass {pass_no}")
    cells = {c["timestamp"]: c for g in batch["grids"] for c in g["cells"]}

    raw_entries = analyzer.analyze_batch(game, pass_no, batch)
    entries = [normalize_entry(r, game, pass_no, batch_no, cells) for r in raw_entries]

    # Replace anything saved earlier for this batch, so re-running is safe.
    source = f"pass{pass_no}"
    log = [e for e in load_log(game["id"])
           if not (e["source"] == source and e["batch"] == batch_no)]
    log = sorted(log + entries, key=lambda e: (e["video_seconds"], e["source"]))
    config.LOGS_DIR.mkdir(exist_ok=True)
    log_path(game["id"]).write_text(json.dumps(log, indent=1))

    progress = load_progress(game["id"])
    state = progress.setdefault(source, {"done_batches": []})
    state["total_batches"] = len(manifest["batches"])
    state["done_batches"] = sorted(set(state["done_batches"]) | {batch_no})
    progress_path(game["id"]).write_text(json.dumps(progress, indent=2))
    missing = len(cells) - len(entries)
    print(f"Saved {len(entries)} entries for pass {pass_no} batch {batch_no}"
          + (f" ({missing} frames not logged)" if missing else ""))


def next_batch(game, pass_no):
    """The first batch not yet logged, or None when the pass is finished."""
    manifest = load_manifest(game["id"], pass_no)
    done = set(load_progress(game["id"]).get(f"pass{pass_no}", {}).get("done_batches", []))
    return next((b for b in manifest["batches"] if b["batch"] not in done), None)


# ---------- command line ----------

def print_status(game):
    progress = load_progress(game["id"])
    for pass_no in (1, 2):
        state = progress.get(f"pass{pass_no}")
        if state:
            print(f"Pass {pass_no}: {len(state['done_batches'])}/{state['total_batches']} batches")
        else:
            print(f"Pass {pass_no}: not started")


def print_next(game, pass_no):
    batch = next_batch(game, pass_no)
    if batch is None:
        print(f"Pass {pass_no} is finished for {game['id']}.")
        return
    kits = game["kit_colors"]
    print(f"Game: {game['id']}  ({game.get('analyzed_team_name')} vs {game.get('other_team_name')})")
    print(f"Analyzed team kit: {kits.get('analyzed_team')}   Other team kit: {kits.get('other_team')}")
    print(f"Analyzed team attacks: 1st half -> {config.attacking_direction(game, 1)}, "
          f"2nd half -> {config.attacking_direction(game, 2)}")
    print(f"Pass {pass_no}, batch {batch['batch']}:")
    for grid in batch["grids"]:
        stamps = ", ".join(f"{c['cell']} {c['timestamp']}" for c in grid["cells"])
        print(f"  {grid['grid']}  [{stamps}]")


def main():
    parser = argparse.ArgumentParser(description="Moment logging (analysis step).")
    parser.add_argument("command", choices=["status", "next", "save"])
    parser.add_argument("--game", required=True)
    parser.add_argument("--pass", dest="pass_no", type=int, default=1, choices=[1, 2])
    parser.add_argument("--batch", type=int)
    parser.add_argument("--input", help="JSON file of raw entries (for save)")
    parser.add_argument("--config", default=str(config.GAMES_FILE))
    args = parser.parse_args()
    game = config.get_game(config.load_config(args.config), args.game)

    if args.command == "status":
        print_status(game)
    elif args.command == "next":
        print_next(game, args.pass_no)
    else:
        if not (args.batch and args.input):
            raise SystemExit("save needs --batch and --input")
        save_batch(game, args.pass_no, args.batch, ManualClaudeCodeAnalyzer(args.input))


if __name__ == "__main__":
    main()
