import json
import threading
import time

import pytest

from src import analyzer, config, extract


def test_screen_to_team_coordinates():
    assert analyzer.to_relative_zone(6, 1, "right") == [6, 1]
    assert analyzer.to_relative_zone(6, 1, "left") == [1, 4]
    assert analyzer.to_relative_xy(90, 20, "left") == [10, 80]


def test_normalize_entry_flips_in_second_half():
    game = config._prepare_game({"id": "g", "second_half_start": "50:00", "attacking_direction": "right"})
    cells = {"55:00": {"video_seconds": 3300, "half": 2, "game_minute": 50.0}}
    entry = analyzer.normalize_entry({"timestamp": "55:00", "ball_screen": [6, 1], "ball_xy_screen": [95, 10],
                                      "possession": "other_team",
                                      "events": ["press", {"type": "Shot", "xy_screen": [90, 50]}]},
                                     game, 1, 3, cells)
    assert entry["ball_zone"] == [1, 4] and entry["ball_xy"] == [5, 90]
    assert entry["events"][0] == {"type": "press", "team": "other_team"}
    assert entry["events"][1]["type"] == "shot" and entry["events"][1]["xy"] == [10, 50]


def test_strict_and_tolerant_normalizing():
    game = config._prepare_game({"id": "g"})
    cells = {"00:04": {"video_seconds": 4, "half": 1, "game_minute": 0.1}}
    raws = [{"timestamp": "00:04"}, {"timestamp": "00:04"}, {"timestamp": "09:99"},
            {"timestamp": "00:04", "view": "sideways"}]
    with pytest.raises(ValueError):
        analyzer.normalize_all(raws, game, 1, 1, cells, strict=True)
    entries, problems = analyzer.normalize_all(raws, game, 1, 1, cells, strict=False)
    assert len(entries) == 1 and len(problems) == 3


@pytest.fixture
def extracted(games):
    game = config.get_game(games, "blue_game")
    manifest = extract.run_pass1(game)
    return game, manifest


def stamps_of(manifest, batch_no):
    batch = manifest["batches"][batch_no - 1]
    return [c["timestamp"] for g in batch["grids"] for c in g["cells"]]


def test_save_entries_replaces_and_tracks_progress(extracted):
    game, manifest = extracted
    stamps = stamps_of(manifest, 1)
    result = analyzer.save_entries(game, 1, 1, [{"timestamp": s, "view": "wide"} for s in stamps[:5]],
                                   usage={"cost": 0.5})
    assert result == {"saved": 5, "missing": len(stamps) - 5, "problems": []}
    analyzer.save_entries(game, 1, 1, [{"timestamp": s, "view": "close"} for s in stamps])
    log = analyzer.load_log("blue_game")
    assert len(log) == len(stamps) and {e["view"] for e in log} == {"close"}
    progress = analyzer.load_progress("blue_game")["pass1"]
    assert progress["done_batches"] == [1] and progress["total_batches"] == 3
    assert progress["usage"]["1"] == {"cost": 0.5}


def test_parallel_saves_never_lose_entries(extracted):
    game, manifest = extracted
    threads = [threading.Thread(target=analyzer.save_entries,
                                args=(game, 1, b, [{"timestamp": s} for s in stamps_of(manifest, b)]))
               for b in (1, 2, 3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(analyzer.load_log("blue_game")) == 42
    assert analyzer.load_progress("blue_game")["pass1"]["done_batches"] == [1, 2, 3]


def test_claims_hand_out_different_batches(extracted, monkeypatch):
    game, _ = extracted
    claimed = [analyzer.claim_batch(game, 1, f"agent{i}")["batch"] for i in range(3)]
    assert claimed == [1, 2, 3]
    assert analyzer.claim_batch(game, 1) is None
    analyzer.save_entries(game, 1, 2, [])                       # saving releases the claim
    assert "2" not in analyzer.load_progress("blue_game")["pass1"]["claims"]
    later = time.time() + (analyzer.CLAIM_MINUTES + 1) * 60     # old claims expire
    monkeypatch.setattr(analyzer.time, "time", lambda: later)
    assert analyzer.claim_batch(game, 1)["batch"] == 1


def test_clear_pass_only_touches_one_pass(project):
    log = [{"source": "pass1", "video_seconds": 1}, {"source": "pass2", "video_seconds": 2}]
    analyzer.write_json(analyzer.log_path("g"), log)
    analyzer.write_json(analyzer.progress_path("g"), {"pass1": {}, "pass2": {}})
    analyzer.clear_pass("g", 2)
    assert analyzer.load_log("g") == [log[0]]
    assert list(analyzer.load_progress("g")) == ["pass1"]


def test_manual_save_from_the_command_line(extracted, tmp_path, monkeypatch, capsys):
    game, manifest = extracted
    entries = tmp_path / "entries.json"
    entries.write_text(json.dumps([{"timestamp": s, "view": "wide"} for s in stamps_of(manifest, 2)]))
    monkeypatch.setattr("sys.argv", ["analyzer", "save", "--game", "blue_game", "--batch", "2",
                                     "--input", str(entries), "--config", str(config.GAMES_FILE)])
    analyzer.main()
    assert "Saved 16 entries for pass 1 batch 2" in capsys.readouterr().out
