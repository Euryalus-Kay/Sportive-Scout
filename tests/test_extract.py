import json

import numpy as np
import pytest
from PIL import Image

from src import analyzer, config, extract


def true_time_error(path, reported):
    """Brightness says the real time (0.1 s steps); how far off is the reported time?"""
    brightness = round(np.asarray(Image.open(path).convert("L"), dtype=float).mean())
    expected = int(np.floor(reported * 10 + 1e-6)) % 256
    return ((brightness - expected + 128) % 256 - 128) / 10


def test_split_range_covers_everything():
    pieces = extract.split_range(10, 500, chunk=240)
    assert pieces == [(10, 240), (250, 240), (490, 20)]
    assert extract.split_range(0, 0) == []


@pytest.mark.parametrize("workers", [1, 4])
def test_frames_have_exact_times(tmp_path, synthetic_video, workers):
    frames = extract.extract_segment(synthetic_video, 7.3, 150, 4, tmp_path, "seg", workers=workers)
    assert len(frames) == 38                                   # 0, 4, ... 148 s after the start
    for i, (path, t) in enumerate(frames):
        assert abs(true_time_error(path, t)) <= 0.1            # label = what the frame shows
        assert 0 <= t - (7.3 + 4 * i) < 0.05                   # no drift at 29.97 fps


def test_parallel_and_sequential_agree(tmp_path, synthetic_video):
    one = extract.extract_segment(synthetic_video, 0, 120, 4, tmp_path / "a", "s", workers=1)
    many = extract.extract_segment(synthetic_video, 0, 120, 4, tmp_path / "b", "s", workers=3)
    assert [round(t, 2) for _, t in one] == [round(t, 2) for _, t in many]


def test_pass1_builds_labeled_grids_and_batches(games):
    game = config.get_game(games, "blue_game")
    manifest = extract.run_pass1(game)
    cells = [c for b in manifest["batches"] for g in b["grids"] for c in g["cells"]]
    assert len(cells) == 22 + 20                                 # 1st half 2-90 s, 2nd half 100-180 s
    assert {c["half"] for c in cells} == {1, 2}
    assert len(manifest["batches"]) == 3                         # 11 grids, 4 per batch in tests
    first = manifest["batches"][0]["grids"][0]
    assert Image.open(config.project_path(first["grid"])).size == (1536, 864)
    for c in cells:
        assert abs(true_time_error(config.project_path(c["frame"]), c["video_seconds"])) <= 0.15
    assert cells[0]["timestamp"] == "00:02" and cells[22]["timestamp"] == "01:40"


def test_pass1_minutes_limit(games):
    manifest = extract.run_pass1(config.get_game(games, "blue_game"), minutes=1)
    cells = [c for b in manifest["batches"] for g in b["grids"] for c in g["cells"]]
    assert len(cells) == 15 and manifest["minutes_limit"] == 1


def test_pass2_windows_around_goals_and_shots(games):
    game = config.get_game(games, "blue_game")
    extract.run_pass1(game)
    log = [{"source": "pass1", "video_seconds": 120.0, "events": [{"type": "shot"}]}]
    (config.LOGS_DIR / "blue_game.json").write_text(json.dumps(log))
    manifest = extract.run_pass2(game)
    assert manifest["moments"] == [[15.0, 40.0], [105.0, 130.0]]   # goal at 0:30, shot at 2:00
    stamps = [c["timestamp"] for g in manifest["batches"][0]["grids"] for c in g["cells"]]
    assert stamps[0] == "00:15" and len(stamps) == 25              # one frame per second


def test_reextracting_clears_that_pass(games):
    game = config.get_game(games, "blue_game")
    manifest = extract.run_pass1(game)
    stamp = manifest["batches"][0]["grids"][0]["cells"][0]["timestamp"]
    analyzer.save_entries(game, 1, 1, [{"timestamp": stamp, "view": "wide"}])
    assert extract.logged_batches("blue_game", 1) == [1]
    extract.run_pass1(game)
    assert extract.logged_batches("blue_game", 1) == []
    assert analyzer.load_log("blue_game") == []


def test_cli_refuses_to_wipe_logged_batches(games, monkeypatch):
    game = config.get_game(games, "blue_game")
    manifest = extract.run_pass1(game)
    stamp = manifest["batches"][0]["grids"][0]["cells"][0]["timestamp"]
    analyzer.save_entries(game, 1, 1, [{"timestamp": stamp, "view": "wide"}])
    monkeypatch.setattr("sys.argv", ["extract", "--game", "blue_game", "--config", str(config.GAMES_FILE)])
    with pytest.raises(SystemExit, match="--force"):
        extract.main()
