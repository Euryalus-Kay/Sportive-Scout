"""Frame extraction and grid building.

Pass 1: one frame every 4 seconds for the whole game, combined into 2x2 grids,
        grouped into batches of 25 grids.
Pass 2: one frame every second around key moments (goals from games.yaml and
        shots found in Pass 1), so shots and goals can be read accurately.

Speed: the film is cut into 4-minute chunks and several ffmpeg processes
decode different chunks at the same time (one per CPU core by default).
Each frame keeps its exact video time, read back from ffmpeg itself.

Usage:
    python -m src.extract --game GAME_ID               # Pass 1, full game
    python -m src.extract --game GAME_ID --minutes 5   # Pass 1, first 5 min
    python -m src.extract --game GAME_ID --pass 2      # Pass 2 key moments
    add --workers N to choose how many ffmpeg processes run at once
"""
import argparse
import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

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
CHUNK_SECONDS = 240     # film per ffmpeg process (a multiple of both intervals)
CELL_NAMES = ["top-left", "top-right", "bottom-left", "bottom-right"]
PTS_TIME = re.compile(r"pts_time:\s*(-?[0-9.]+)")


def default_workers():
    """How many ffmpeg processes to run at once: one per core, at most 8."""
    return max(1, min(8, os.cpu_count() or 2))


# ---------- ffmpeg helpers ----------

def video_duration(path):
    """Length of a video in seconds, using ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def split_range(start, duration, chunk=CHUNK_SECONDS):
    """Cut [start, start+duration) into (chunk_start, chunk_length) pieces."""
    pieces, offset = [], 0.0
    while offset < duration - 1e-6:
        pieces.append((start + offset, min(chunk, duration - offset)))
        offset += chunk
    return pieces


def extract_chunk(video, start, duration, interval, out_dir, prefix, threads=0):
    """One ffmpeg run: the first frame of every `interval` seconds of a stretch.

    Returns a list of (image_path, video_seconds) with the exact time of each
    frame (ffmpeg's showinfo filter prints it), so labels never drift.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / f"{prefix}_%04d.jpg"
    # Keep a frame whenever floor(t / interval) changes: frame i is the first
    # frame at or after start + i*interval, whatever the video's frame rate.
    select = f"select='isnan(prev_t)+gt(floor(t/{interval})\\,floor(prev_t/{interval}))'"
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "info", "-y",
           "-threads", str(threads), "-ss", f"{start:.3f}", "-i", str(video),
           "-t", f"{duration:.3f}", "-map", "0:v:0",
           "-vf", f"{select},showinfo,scale={FRAME_WIDTH}:-2",
           "-fps_mode", "vfr", "-q:v", "4", str(pattern)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-5:])
        raise RuntimeError(f"ffmpeg failed on {video.name} at {config.format_time(start)}:\n{tail}")
    times = [float(m.group(1)) for line in result.stderr.splitlines()
             if "showinfo" in line and (m := PTS_TIME.search(line))]
    files = sorted(out_dir.glob(f"{prefix}_*.jpg"))
    # showinfo prints one line per kept frame, in order. If ffmpeg ever skips a
    # line, fall back to the planned time for the frames without one.
    frames = [(f, start + (times[i] if i < len(times) else i * interval)) for i, f in enumerate(files)]
    # -t can let one frame past the end through; it belongs to the next chunk.
    for path, _ in [fr for fr in frames if fr[1] >= start + duration - 1e-3]:
        path.unlink()
    return [fr for fr in frames if fr[1] < start + duration - 1e-3]


def extract_segment(video, start, duration, interval, out_dir, prefix, workers=None, progress=None):
    """Pull one frame every `interval` seconds from [start, start+duration).

    The stretch is split into chunks that run on several ffmpeg processes at
    once. Returns a list of (image_path, video_seconds), in time order.
    """
    workers = workers or default_workers()
    pieces = split_range(start, duration)
    threads = max(1, (os.cpu_count() or 2) // workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_chunk, video, s, d, interval, out_dir,
                               f"{prefix}_c{i:03d}", threads): i
                   for i, (s, d) in enumerate(pieces)}
        results = {}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
            if progress:
                progress(len(results), len(pieces))
    return [frame for i in sorted(results) for frame in results[i]]


# ---------- grid building ----------

def _font(size):
    """A readable font, falling back to Pillow's built-in one."""
    for name in ["/System/Library/Fonts/Helvetica.ttc", "Arial.ttf", "DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
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
        grid.paste(img.resize((w, h)) if img.size != (w, h) else img, (x, y))
        label = cell_label(game, video_s)
        box = draw.textbbox((x + 8, y + 8), label, font=font)
        draw.rectangle((box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4), fill="black")
        draw.text((x + 8, y + 8), label, fill="yellow", font=font)
    grid.save(out_path, quality=80)


def build_batches(frames, game, pass_dir, workers=None):
    """Turn a frame list into grids and batches. Returns the manifest batches."""
    grids = [frames[i:i + GRID_SIZE] for i in range(0, len(frames), GRID_SIZE)]
    jobs, batches = [], []
    for b in range(0, len(grids), GRIDS_PER_BATCH):
        batch_no = len(batches) + 1
        batch_dir = pass_dir / f"batch_{batch_no:03d}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        for g, grid_frames in enumerate(grids[b:b + GRIDS_PER_BATCH], start=1):
            grid_path = batch_dir / f"grid_{g:03d}.jpg"
            jobs.append((grid_frames, grid_path))
            entries.append({
                "grid": _rel(grid_path),
                "cells": [_cell_info(game, CELL_NAMES[i], s, path)
                          for i, (path, s) in enumerate(grid_frames)],
            })
        batches.append({"batch": batch_no, "grids": entries})
    with ThreadPoolExecutor(max_workers=workers or default_workers()) as pool:
        list(pool.map(lambda job: build_grid(job[0], game, job[1]), jobs))
    return batches


def _cell_info(game, cell, video_s, frame_path):
    return {
        "cell": cell,
        "timestamp": config.format_time(video_s),
        "video_seconds": round(video_s, 1),
        "half": config.half_for(game, video_s),
        "game_minute": round(config.game_minute(game, video_s), 1),
        "frame": _rel(frame_path),
    }


def _rel(path):
    """Path relative to the project folder (what manifests store)."""
    try:
        return str(path.relative_to(config.ROOT))
    except ValueError:
        return str(path)


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
    return [(s, length) for s, length in segments if length > 0]


def run_pass1(game, minutes=None, workers=None, progress=None):
    """Extract Pass 1 frames and grids. Returns the manifest."""
    video = config.FILM_DIR / game["file"]
    pass_dir = _fresh_dir(game, "pass1")
    raw_dir = pass_dir / "raw"
    segments = pass1_segments(game, video_duration(video), minutes)
    total = sum(len(split_range(s, d)) for s, d in segments)
    frames, done = [], 0
    for i, (start, length) in enumerate(segments):
        offset = done
        frames += extract_segment(video, start, length, PASS1_INTERVAL, raw_dir, f"seg{i + 1}",
                                  workers, _shifted(progress, offset, total))
        done += len(split_range(start, length))
    batches = build_batches(frames, game, pass_dir, workers)
    manifest = _write_manifest(game, pass_dir, 1, PASS1_INTERVAL, batches, minutes=minutes)
    print(f"Pass 1: {len(frames)} frames -> "
          f"{sum(len(b['grids']) for b in batches)} grids in {len(batches)} batches")
    return manifest


def _shifted(progress, offset, total):
    """Progress callback for one segment, counted inside the whole pass."""
    if not progress:
        return None
    return lambda done, _: progress(offset + done, total)


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


def run_pass2(game, workers=None, progress=None):
    """Extract 1-second frames around every key moment. Returns the manifest."""
    video = config.FILM_DIR / game["file"]
    pass_dir = _fresh_dir(game, "pass2")
    duration = video_duration(video)
    moments = key_moments(game)
    windows = [(max(0.0, start), min(end, duration)) for start, end in moments if start < duration]

    def one_window(i, start, end):
        frames = extract_chunk(video, start, end - start, PASS2_INTERVAL,
                               pass_dir / "raw", f"moment{i:03d}")
        moment_batches = build_batches(frames, game, pass_dir / f"moment_{i:03d}", workers=1)
        return {"batch": i, "window": [config.format_time(start), config.format_time(end)],
                "grids": [g for b in moment_batches for g in b["grids"]]}

    with ThreadPoolExecutor(max_workers=workers or default_workers()) as pool:
        futures = [pool.submit(one_window, i, s, e) for i, (s, e) in enumerate(windows, start=1)]
        batches = []
        for future in as_completed(futures):
            batches.append(future.result())
            if progress:
                progress(len(batches), len(windows))
    batches = sorted((b for b in batches if b["grids"]), key=lambda b: b["batch"])
    manifest = _write_manifest(game, pass_dir, 2, PASS2_INTERVAL, batches,
                               moments=[[round(s, 1), round(e, 1)] for s, e in moments])
    print(f"Pass 2: {len(batches)} key moments, "
          f"{sum(len(b['grids']) for b in batches)} grids")
    return manifest


# ---------- shared ----------

def logged_batches(game_id, pass_no):
    """Batches of a pass that already have log entries saved."""
    path = config.LOGS_DIR / f"{game_id}_progress.json"
    if not path.exists():
        return []
    return json.loads(path.read_text()).get(f"pass{pass_no}", {}).get("done_batches", [])


def _fresh_dir(game, name):
    """Empty frames/<game>/<pass>/ so old frames never mix with new ones.

    New frames mean new batch numbers, so the old log entries and progress of
    that pass are cleared too (the CLI asks for --force before doing that).
    """
    path = config.FRAMES_DIR / game["id"] / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    from src.analyzer import clear_pass   # here to avoid a circular import
    clear_pass(game["id"], int(name[-1]))
    return path


def _write_manifest(game, pass_dir, pass_no, interval, batches, minutes=None, **extra):
    manifest = {"game": game["id"], "pass": pass_no, "interval_seconds": interval,
                "minutes_limit": minutes, "video": game["file"], **extra, "batches": batches}
    (pass_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Extract frames and build grids.")
    parser.add_argument("--game", required=True, help="game id from games.yaml")
    parser.add_argument("--pass", dest="pass_no", type=int, default=1, choices=[1, 2])
    parser.add_argument("--minutes", type=float, help="only the first N minutes (Pass 1)")
    parser.add_argument("--workers", type=int, help=f"ffmpeg processes at once (default {default_workers()})")
    parser.add_argument("--force", action="store_true", help="re-extract even if batches were already logged")
    parser.add_argument("--config", default=str(config.GAMES_FILE))
    args = parser.parse_args()
    game = config.get_game(config.load_config(args.config), args.game)
    if not (config.FILM_DIR / game["file"]).exists():
        raise SystemExit(f"Video not found: film/{game['file']}")
    logged = logged_batches(game["id"], args.pass_no)
    if logged and not args.force:
        raise SystemExit(f"Pass {args.pass_no} of {game['id']} already has {len(logged)} logged "
                         "batches. Re-extracting clears them. Add --force to do it anyway.")
    if args.pass_no == 1:
        run_pass1(game, args.minutes, args.workers)
    else:
        run_pass2(game, args.workers)


if __name__ == "__main__":
    main()
