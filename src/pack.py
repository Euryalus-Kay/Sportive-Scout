"""Analysis packs: games.yaml and the logs in one .zip, without the film.

A pack opens the finished analysis somewhere else, like the app on the website,
which runs inside the browser: the file is read there and never uploaded, so a
scouting report can be viewed or shared without publishing it.

    python -m src.pack                       # writes reports/analysis_pack.zip
    python -m src.pack my_team.zip
"""
import argparse
import io
import zipfile
from pathlib import Path

from src import config


def build_pack(out_path=None, games_file=None, logs_dir=None):
    """Zip games.yaml and the log of every game in it. Returns the path."""
    games_file = Path(games_file or config.GAMES_FILE)
    logs_dir = Path(logs_dir or config.LOGS_DIR)
    out_path = Path(out_path or config.REPORTS_DIR / "analysis_pack.zip")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = config.load_config(games_file)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as pack:
        pack.write(games_file, "games.yaml")
        for game in cfg["games"]:
            log = logs_dir / f"{game['id']}.json"
            if log.exists():
                pack.write(log, f"logs/{log.name}")
    return out_path


def open_pack(data, games_file=None, logs_dir=None):
    """Unpack a pack (bytes) as games.yaml and logs/. Returns the number of logs.

    Only games.yaml and logs/<name>.json are read, so a pack can't write anywhere else.
    """
    games_file = Path(games_file or config.GAMES_FILE)
    logs_dir = Path(logs_dir or config.LOGS_DIR)
    with zipfile.ZipFile(io.BytesIO(data)) as pack:
        names = pack.namelist()
        if "games.yaml" not in names:
            raise ValueError("This file isn't a Sportive Scout analysis (it has no games.yaml).")
        logs = [n for n in names if n.startswith("logs/") and n.endswith(".json")
                and "/" not in n[len("logs/"):] and ".." not in n]
        games = pack.read("games.yaml")
        contents = {n: pack.read(n) for n in logs}
    games_file.write_bytes(games)
    config.load_config(games_file)                   # stops with a clear error if it can't be read
    logs_dir.mkdir(exist_ok=True)
    for name, body in contents.items():
        (logs_dir / name[len("logs/"):]).write_bytes(body)
    return len(logs)


def main():
    parser = argparse.ArgumentParser(description="Pack games.yaml and the logs into one .zip.")
    parser.add_argument("out", nargs="?", help="where to write it (default reports/analysis_pack.zip)")
    path = build_pack(parser.parse_args().out)
    print(f"Wrote {path} ({path.stat().st_size // 1024} KB). Open it on the website's app with "
          "\"Open your analysis\"; it stays in your browser.")


if __name__ == "__main__":
    main()
