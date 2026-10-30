"""One command for the whole analysis of a game (needs a Claude API key).

    python -m src.run --game GAME_ID              # everything for one game
    python -m src.run --all                       # every game in games.yaml, then reports
    python -m src.run --game GAME_ID --minutes 5  # quick test on the first 5 minutes
    python -m src.run --all --estimate            # only print what it would cost

Steps, each one skipped when it is already done (so running again resumes):
  1. Pass 1 frames: one every 4 s, several ffmpeg processes at once
  2. Pass 1 analysis: many Claude requests at once (src/batch_runner.py)
  3. Pass 2 frames: one every second around goals and the shots from step 2
  4. Pass 2 analysis
  5. Reports and the game plan

Without an API key, do the steps by hand and let Claude Code log the
batches instead (see CLAUDE.md).
"""
import argparse
import json
import math
import sys
from dataclasses import dataclass

from src import config, extract, report
from src.analyzer import FatalAnalysisError, load_log
from src.api_analyzer import (DEFAULT_EFFORT, DEFAULT_MODEL, EFFORTS, MODELS, ApiAnalyzer,
                              api_key_available, estimate_cost)
from src.batch_runner import DEFAULT_WORKERS, GRIDS_PER_CHUNK, pending_grids, run_pass

STAGES = {"extract1": "Pass 1 frames", "analyze1": "Pass 1 analysis",
          "extract2": "Pass 2 frames", "analyze2": "Pass 2 analysis"}


@dataclass
class Options:
    minutes: float = None            # only the first N minutes (a quick test)
    workers: int = DEFAULT_WORKERS   # Claude requests at once
    extract_workers: int = None      # ffmpeg processes at once (default: one per core)
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    grids_per_chunk: int = GRIDS_PER_CHUNK
    pass2: bool = True
    re_extract: bool = False


# ---------- what is already done ----------

def manifest_of(game_id, pass_no):
    path = config.FRAMES_DIR / game_id / f"pass{pass_no}" / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else None


def pass1_ready(game, minutes=None):
    """True when Pass 1 frames exist for the same video and length."""
    m = manifest_of(game["id"], 1)
    return bool(m) and m.get("minutes_limit") == minutes and m.get("video", game["file"]) == game["file"]


def pass2_ready(game):
    """True when Pass 2 frames exist for exactly the key moments known now."""
    m = manifest_of(game["id"], 2)
    wanted = [[round(s, 1), round(e, 1)] for s, e in extract.key_moments(game)]
    return bool(m) and m.get("moments") == wanted


def planned_grids(game, minutes=None):
    """Pass 1 grids a game will have (from the video length), before extracting."""
    video = config.FILM_DIR / game["file"]
    seconds = sum(length for _, length in extract.pass1_segments(game, extract.video_duration(video), minutes))
    return math.ceil(seconds / extract.PASS1_INTERVAL / extract.layout(game)[1])


# ---------- running ----------

def analyze_game(game, opts, progress=None, stop=None, confirm=None, analyzer=None):
    """Run every step for one game. Returns a summary dict.

    progress(event) gets {"stage", "done", "total", ...} updates. confirm(cost,
    grids) is asked before paying for Pass 1 analysis; returning False stops.
    """
    emit = progress or (lambda event: None)
    analyzer = analyzer or ApiAnalyzer(opts.model, opts.effort)
    summary = {"game": game["id"], "cost": 0.0, "failed": [], "problems": [], "stopped": False}

    if opts.re_extract or not pass1_ready(game, opts.minutes):
        emit({"stage": "extract1", "done": 0, "total": 1})
        extract.run_pass1(game, opts.minutes, opts.extract_workers,
                          progress=lambda d, t: emit({"stage": "extract1", "done": d, "total": t}))

    grids = pending_grids(game["id"], 1)
    if confirm and grids and not confirm(estimate_cost(grids, opts.model, opts.grids_per_chunk,
                                             extract.layout(game)[1]), grids):
        summary["stopped"] = True
        return summary
    if not _analyze(game, 1, analyzer, opts, emit, stop, summary) or not opts.pass2:
        return summary

    if opts.re_extract or not pass2_ready(game):
        emit({"stage": "extract2", "done": 0, "total": 1})
        extract.run_pass2(game, opts.extract_workers,
                          progress=lambda d, t: emit({"stage": "extract2", "done": d, "total": t}))
    _analyze(game, 2, analyzer, opts, emit, stop, summary)
    return summary


def _analyze(game, pass_no, analyzer, opts, emit, stop, summary):
    """Analyze one pass and add it to the summary. False means stop here."""
    result = run_pass(game, pass_no, analyzer, opts.workers, opts.grids_per_chunk, emit, stop)
    summary["cost"] += result.cost
    summary["failed"] += [f"pass {pass_no} {name}: {why}" for name, why in result.failed]
    summary["problems"] += result.problems
    summary[f"pass{pass_no}"] = {"saved_batches": len(result.saved_batches), "seconds": result.seconds,
                                 "chunks": result.total_chunks, "cached": result.cached_chunks}
    if result.fatal:
        raise FatalAnalysisError(result.fatal)
    summary["stopped"] = result.stopped
    return not result.stopped


def build_reports(cfg):
    """Write reports for the matchup when any game has logs. Returns True if written."""
    if not any(load_log(g["id"]) for g in cfg["games"]):
        return False
    config.REPORTS_DIR.mkdir(exist_ok=True)
    report.build(cfg, config.LOGS_DIR, config.REPORTS_DIR)
    return True


# ---------- command line ----------

class ProgressPrinter:
    """Draws one progress line per stage in the terminal."""

    def __init__(self):
        self.stage = None

    def __call__(self, event):
        if event["stage"] != self.stage:
            if self.stage:
                print()
            self.stage = event["stage"]
        done, total = event["done"], max(1, event["total"])
        bar = "#" * int(24 * done / total)
        extra = f"  ${event['cost']:.2f}" if "cost" in event else ""
        extra += f"  {event['failed']} failed" if event.get("failed") else ""
        extra += f"  about {_duration(event['eta'])} left" if event.get("eta") else ""
        sys.stdout.write(f"\r{STAGES.get(self.stage, self.stage):<16} [{bar:<24}] {done}/{total}{extra}   ")
        sys.stdout.flush()

    def end(self):
        if self.stage:
            print()
        self.stage = None


def _duration(seconds):
    seconds = int(seconds)
    return f"{seconds // 60}m{seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


def print_estimate(games, opts):
    total = 0.0
    for game in games:
        grids = pending_grids(game["id"], 1) if pass1_ready(game, opts.minutes) else planned_grids(game, opts.minutes)
        per = extract.layout(game)[1]
        cost = estimate_cost(grids, opts.model, opts.grids_per_chunk, per)
        total += cost
        print(f"{game['id']}: {grids * per} frames left for Pass 1, about ${cost:.2f}")
    print(f"Total with {MODELS[opts.model]['label']}: about ${total:.2f} "
          "(Pass 2 key moments usually add 10-20%). This is a rough estimate.")


def main():
    parser = argparse.ArgumentParser(description="Analyze games end to end with the Claude API.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--game", help="game id from games.yaml")
    target.add_argument("--all", action="store_true", help="every game in games.yaml")
    parser.add_argument("--minutes", type=float, help="only the first N minutes (quick test)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Claude requests at once")
    parser.add_argument("--extract-workers", type=int, help="ffmpeg processes at once")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODELS))
    parser.add_argument("--effort", default=DEFAULT_EFFORT, choices=EFFORTS)
    parser.add_argument("--grids-per-request", type=int, default=GRIDS_PER_CHUNK)
    parser.add_argument("--no-pass2", action="store_true", help="skip the key-moment pass")
    parser.add_argument("--re-extract", action="store_true", help="extract frames again (clears that pass's logs)")
    parser.add_argument("--estimate", action="store_true", help="only print the cost estimate")
    parser.add_argument("--yes", action="store_true", help="don't ask before spending")
    parser.add_argument("--config", default=str(config.GAMES_FILE))
    args = parser.parse_args()

    cfg = config.load_config(args.config)
    problems = config.validate_config(cfg)
    if problems:
        raise SystemExit("Fix games.yaml first:\n- " + "\n- ".join(problems))
    games = cfg["games"] if args.all else [config.get_game(cfg, args.game)]
    games = [g for g in games if (config.FILM_DIR / g["file"]).exists() or print(f"Skipping {g['id']}: film/{g['file']} not found")]
    opts = Options(args.minutes, args.workers, args.extract_workers, args.model, args.effort,
                   args.grids_per_request, not args.no_pass2, args.re_extract)
    if args.estimate:
        return print_estimate(games, opts)
    if not api_key_available():
        raise SystemExit("No API key found. Put ANTHROPIC_API_KEY=... in a .env file in the project "
                         "folder, or let Claude Code log the batches by hand (see CLAUDE.md).")

    printer = ProgressPrinter()

    def confirm(cost, grids):
        if args.yes:
            return True
        printer.end()
        answer = input(f"Analyze {grids} grids ({grids * 4} frames) with {MODELS[opts.model]['label']}? "
                       f"Rough cost ${cost:.2f}. [y/N] ")
        return answer.strip().lower() in ("y", "yes")

    total = 0.0
    for game in games:
        print(f"== {game['id']} ==")
        try:
            summary = analyze_game(game, opts, printer, confirm=confirm)
        except FatalAnalysisError as err:
            printer.end()
            raise SystemExit(f"Stopped: {err}")
        printer.end()
        total += summary["cost"]
        for line in summary["failed"]:
            print(f"  not analyzed: {line}")
        if summary["failed"]:
            print("  Run the same command again to retry what failed.")
        print(f"  cost this run: ${summary['cost']:.2f}")
    if build_reports(cfg):
        print(f"Reports written to {config.REPORTS_DIR.relative_to(config.ROOT)}/")
    print(f"Total cost this run: ${total:.2f}")


if __name__ == "__main__":
    main()
