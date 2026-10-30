"""The film behind a moment: the extracted frame, a short clip, or a preview.

The app uses these so any stat can be checked on film with one click.
"""
import json
import subprocess
from functools import lru_cache

from PIL import Image

from src import config

CLIP_BEFORE, CLIP_AFTER = 8, 4      # seconds of film around a moment
CLIP_HEIGHT = 540
CELL_BOXES = {"top-left": (0, 0), "top-right": (1, 0), "bottom-left": (0, 1), "bottom-right": (1, 1)}


def _manifest_paths(game_id):
    return [config.FRAMES_DIR / game_id / f"pass{n}" / "manifest.json" for n in (2, 1)]


@lru_cache(maxsize=32)
def _cells(game_id, stamp):
    """Every extracted frame of a game: (video seconds, frame path, grid path, cell)."""
    cells = []
    for path in _manifest_paths(game_id):
        if path.exists():
            for batch in json.loads(path.read_text())["batches"]:
                for grid in batch["grids"]:
                    cells += [(c["video_seconds"], c.get("frame"), grid["grid"], c["cell"]) for c in grid["cells"]]
    return cells


def find_frame(game_id, seconds, tolerance=2.5):
    """The extracted frame nearest to a video time (a path or an image), or None."""
    if not game_id or seconds is None:
        return None
    stamp = tuple(p.stat().st_mtime for p in _manifest_paths(game_id) if p.exists())
    cells = _cells(game_id, stamp)
    if not cells:
        return None
    t, frame, grid, cell = min(cells, key=lambda c: abs(c[0] - seconds))
    if abs(t - seconds) > tolerance:
        return None
    if frame and config.project_path(frame).exists():
        return config.project_path(frame)
    grid_path = config.project_path(grid)       # older manifests: cut the cell out of its grid
    if not grid_path.exists():
        return None
    image = Image.open(grid_path)
    w, h = image.width // 2, image.height // 2
    col, row = CELL_BOXES[cell]
    return image.crop((col * w, row * h, col * w + w, row * h + h))


def film_path(game):
    path = config.FILM_DIR / game["file"]
    return path if path.exists() else None


def cut_clip(game, seconds):
    """A short, small mp4 around a moment (cached in frames/<game>/clips/). None without film."""
    video = film_path(game)
    if video is None or seconds is None:
        return None
    start = max(0.0, seconds - CLIP_BEFORE)
    out = config.FRAMES_DIR / game["id"] / "clips" / f"{int(round(seconds))}.mp4"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{start:.2f}", "-i", str(video),
                    "-t", f"{CLIP_BEFORE + CLIP_AFTER}", "-vf", f"scale=-2:{CLIP_HEIGHT}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-b:a", "96k",
                    "-movflags", "+faststart", str(tmp)], check=True)
    tmp.replace(out)
    return out


def preview_frame(video, seconds, width=640):
    """One frame of a video as JPEG bytes (to find kickoff and halftime times)."""
    result = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{max(0.0, seconds):.2f}", "-i", str(video),
                             "-frames:v", "1", "-vf", f"scale={width}:-2", "-f", "image2", "-c:v", "mjpeg", "pipe:1"],
                            capture_output=True, check=True)
    return result.stdout


def video_info(video):
    """{"duration", "width", "height", "fps"} from ffprobe."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(video)],
                         capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    stream = data["streams"][0]
    num, den = (stream.get("r_frame_rate") or "0/1").split("/")
    return {"duration": float(data["format"]["duration"]), "width": stream["width"],
            "height": stream["height"], "fps": float(num) / float(den or 1)}
