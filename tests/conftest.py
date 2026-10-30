"""Shared test setup: a throwaway project folder and a small synthetic video."""
import shutil
import subprocess

import pytest
import yaml

from src import config, extract

SYNTHETIC_SECONDS = 180


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Point every folder the app uses at a temporary one, so tests never touch real data."""
    for name, sub in [("FILM_DIR", "film"), ("FRAMES_DIR", "frames"),
                      ("LOGS_DIR", "logs"), ("REPORTS_DIR", "reports")]:
        path = tmp_path / sub
        path.mkdir()
        monkeypatch.setattr(config, name, path)
    monkeypatch.setattr(config, "GAMES_FILE", tmp_path / "games.yaml")
    return tmp_path


@pytest.fixture(scope="session")
def synthetic_video(tmp_path_factory):
    """3 minutes of 29.97 fps video whose brightness is the time (0.1 s steps, wraps at 25.6 s)."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    path = tmp_path_factory.mktemp("video") / "synthetic.mp4"
    source = (f"color=c=black:s=320x180:r=30000/1001:d={SYNTHETIC_SECONDS},format=gray,"
              "geq=lum='mod(floor(T*10)\\,256)'")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", source,
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "1", "-g", "120",
                    "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def game_entry(game_id, team, other, direction="right", goals=()):
    return {
        "id": game_id, "file": "match.mp4", "team_analyzed": "us" if team == "Blue" else "opponent",
        "analyzed_team_name": team, "other_team_name": other,
        "kit_colors": {"analyzed_team": f"{team.lower()} shirts", "other_team": f"{other.lower()} shirts"},
        "attacking_direction": direction, "kickoff_time": "00:02", "first_half_end": "01:30",
        "second_half_start": "01:40", "final_score": "1-0", "goal_times": list(goals),
        "playoff": False, "opponent_strength": "similar", "notes": "",
    }


@pytest.fixture
def games(project, synthetic_video, monkeypatch):
    """games.yaml with two games on the synthetic video (one per team), small batches."""
    shutil.copy(synthetic_video, project / "film" / "match.mp4")
    monkeypatch.setattr(extract, "GRIDS_PER_BATCH", 4)     # several batches from a short video
    data = {"matchup": {"our_team": "Blue", "opponent": "Red"},
            "games": [game_entry("blue_game", "Blue", "Green",
                                 goals=[{"time": "00:30", "team": "analyzed_team", "position": "ST", "how": "counter"}]),
                      game_entry("red_game", "Red", "Yellow", direction="left")]}
    config.GAMES_FILE.write_text(yaml.safe_dump(data, sort_keys=False))
    return config.load_config(config.GAMES_FILE)


@pytest.fixture
def no_sleep(monkeypatch):
    """Skip the waits between retries."""
    import src.api_analyzer as api
    monkeypatch.setattr(api.time, "sleep", lambda seconds: None)
