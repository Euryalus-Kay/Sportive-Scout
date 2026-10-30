"""Frame extraction and grid building.

Pass 1: one frame every 4 seconds for the whole game, combined into 2x2 grids,
        grouped into batches of 25 grids.
Pass 2: one frame every second around key moments (goals from games.yaml and
        shots found in Pass 1), so shots and goals can be read accurately.

Usage:
    python -m src.extract --game GAME_ID               # Pass 1, full game
    python -m src.extract --game GAME_ID --minutes 5   # Pass 1, first 5 min
    python -m src.extract --game GAME_ID --pass 2      # Pass 2 key moments
"""
import argparse
import json
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

from src import config

PASS1_INTERVAL = 4      # seconds between frames
PASS2_INTERVAL = 1
PASS2_BEFORE = 15       # seconds of film before a key moment
PASS2_AFTER = 10
MERGE_GAP = 20          # key moments closer than this share one window
FRAME_WIDTH = 768
GRID_SIZE = 4           # frames per grid (2x2)
GRIDS_PER_BATCH = 25
CELL_NAMES = ["top-left", "top-right", "bottom-left", "bottom-right"]


# ---------- ffmpeg helpers ----------

def video_duration(path):
    """Length of a video in seconds, using ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def extract_segment(video, start, duration, interval, out_dir, prefix):
    """Pull one frame every `interval` seconds from [start, start+duration).

    Returns a list of (image_path, video_seconds).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / f"{prefix}_%05d.jpg"
    # Keep the first frame at or after every `interval` seconds, so each image's
    # time is exact (the fps filter would shift frames by up to a few seconds).
    select = f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{interval - 0.01})'"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y",
         "-ss", f"{start:.2f}", "-i", str(video), "-t", f"{duration:.2f}",
         "-vf", f"{select},scale={FRAME_WIDTH}:-2", "-fps_mode", "vfr", "-q:v", "4",
         str(pattern)],
        check=True,
    )
    files = sorted(out_dir.glob(f"{prefix}_*.jpg"))
    return [(f, start + i * interval) for i, f in enumerate(files)]


# ---------- grid building ----------

def _font(size):
    """A readable font, falling back to Pillow's built-in one."""
    for name in ["/System/Library/Fonts/Helvetica.ttc", "Arial.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def cell_label(game, video_s):
    """Label like "12:34 | 1H 10'" (video time, half, game minute)."""
    half = config.half_for(game, video_s)
    half_txt = {0: "break", 1: "1H", 2: "2H"}[half]
    minute = int(config.game_minute(game, video_s))
    return f"{config.format_time(video_s)} | {half_txt} {minute}'"


def build_grid(frames, game, out_path):
    """Combine up to 4 frames into one 2x2 image, each labeled with its time."""
    images = [Image.open(path) for path, _ in frames]
    w, h = images[0].size
    grid = Image.new("RGB", (w * 2, h * 2), "black")
    draw = ImageDraw.Draw(grid)
    font = _font(28)
    for i, (img, (_, video_s)) in enumerate(zip(images, frames)):
        x, y = (i % 2) * w, (i // 2) * h
        grid.paste(img, (x, y))
        label = cell_label(game, video_s)
        box = draw.textbbox((x + 8, y + 8), label, font=font)
        draw.rectangle((box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4), fill="black")
        draw.text((x + 8, y + 8), label, fill="yellow", font=font)
    grid.save(out_path, quality=80)


def build_batches(frames, game, pass_dir, batch_names=None):
    """Turn a frame list into grids and batches. Returns the manifest batches.

    `batch_names` lets Pass 2 give each key moment its own batch.
    """
    grids = [frames[i:i + GRID_SIZE] for i in range(0, len(frames), GRID_SIZE)]
    batches = []
    for b in range(0, len(grids), GRIDS_PER_BATCH):
        batch_no = len(batches) + 1
        batch_dir = pass_dir / f"batch_{batch_no:03d}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        for g, grid_frames in enumerate(grids[b:b + GRIDS_PER_BATCH], start=1):
            grid_path = batch_dir / f"grid_{g:03d}.jpg"
            build_grid(grid_frames, game, grid_path)
            entries.append({
                "grid": str(grid_path.relative_to(config.ROOT)),
                "cells": [_cell_info(game, CELL_NAMES[i], s)
                          for i, (_, s) in enumerate(grid_frames)],
            })
        batches.append({"batch": batch_no, "grids": entries})
    return batches


def _cell_info(game, cell, video_s):
    return {
        "cell": cell,
        "timestamp": config.format_time(video_s),
        "video_seconds": round(video_s, 1),
        "half": config.half_for(game, video_s),
        "game_minute": round(config.game_minute(game, video_s), 1),
    }


# ---------- Pass 1 ----------

def pass1_segments(game, duration, minutes=None):
    """The (start, length) stretches of video to scan: each half, no break."""
    kickoff = game["kickoff_s"]
    if minutes:
        return [(kickoff, min(minutes * 60, duration - kickoff))]
    second = game["second_half_start_s"]
    first_end = game["first_half_end_s"] or second or duration
    segments = [(kickoff, first_end - kickoff)]
    if second is not None:
        segments.append((second, duration - second))
    return segments


def run_pass1(game, minutes=None):
    video = config.FILM_DIR / game["file"]
    pass_dir = _fresh_dir(game, "pass1")
    raw_dir = pass_dir / "raw"
    frames = []
    for i, (start, length) in enumerate(pass1_segments(game, video_duration(video), minutes)):
        frames += extract_segment(video, start, length, PASS1_INTERVAL, raw_dir, f"seg{i + 1}")
    batches = build_batches(frames, game, pass_dir)
    _write_manifest(game, pass_dir, 1, PASS1_INTERVAL, batches, minutes=minutes)
    print(f"Pass 1: {len(frames)} frames -> "
          f"{sum(len(b['grids']) for b in batches)} grids in {len(batches)} batches")


# ---------- Pass 2 ----------

def key_moments(game):
    """Video times worth a closer look: goals from games.yaml + shots in the log."""
    times = [g["seconds"] for g in game["goal_times"] if g.get("seconds") is not None]
    log_path = config.LOGS_DIR / f"{game['id']}.json"
    if log_path.exists():
        for entry in json.loads(log_path.read_text()):
            if entry.get("source") == "pass1" and any(
                    e["type"] in ("shot", "goal") for e in entry.get("events", [])):
                times.append(entry["video_seconds"])
    merged = []
    for t in sorted(times):
        if merged and t - merged[-1][-1] <= MERGE_GAP:
            merged[-1].append(t)
        else:
            merged.append([t])
    return [(group[0] - PASS2_BEFORE, group[-1] + PASS2_AFTER) for group in merged]


def run_pass2(game):
    video = config.FILM_DIR / game["file"]
    pass_dir = _fresh_dir(game, "pass2")
    batches = []
    for i, (start, end) in enumerate(key_moments(game), start=1):
        start = max(0.0, start)
        frames = extract_segment(video, start, end - start, PASS2_INTERVAL,
                                 pass_dir / "raw", f"moment{i:03d}")
        moment_batches = build_batches(frames, game, pass_dir / f"moment_{i:03d}")
        grids = [g for b in moment_batches for g in b["grids"]]
        batches.append({"batch": i, "window": [config.format_time(start),
                                               config.format_time(end)], "grids": grids})
    _write_manifest(game, pass_dir, 2, PASS2_INTERVAL, batches)
    print(f"Pass 2: {len(batches)} key moments, "
          f"{sum(len(b['grids']) for b in batches)} grids")


# ---------- shared ----------

def _fresh_dir(game, name):
    """Empty frames/<game>/<pass>/ so old frames never mix with new ones."""
    path = config.FRAMES_DIR / game["id"] / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def _write_manifest(game, pass_dir, pass_no, interval, batches, minutes=None):
    manifest = {"game": game["id"], "pass": pass_no, "interval_seconds": interval,
                "minutes_limit": minutes, "batches": batches}
    (pass_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Extract frames and build grids.")
    parser.add_argument("--game", required=True, help="game id from games.yaml")
    parser.add_argument("--pass", dest="pass_no", type=int, default=1, choices=[1, 2])
    parser.add_argument("--minutes", type=float, help="only the first N minutes (Pass 1)")
    parser.add_argument("--config", default=str(config.GAMES_FILE))
    args = parser.parse_args()
    game = config.get_game(config.load_config(args.config), args.game)
    if not (config.FILM_DIR / game["file"]).exists():
        raise SystemExit(f"Video not found: film/{game['file']}")
    if args.pass_no == 1:
        run_pass1(game, args.minutes)
    else:
        run_pass2(game)


if __name__ == "__main__":
    main()
