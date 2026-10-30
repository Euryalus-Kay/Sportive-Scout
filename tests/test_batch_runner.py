import threading
import time

import pytest

from src import analyzer, config, extract
from src.api_analyzer import ApiAnalyzer
from src.batch_runner import cache_dir, pending_grids, plan_chunks, run_pass
from tests.fake_api import FakeClaude, error_response


@pytest.fixture
def game(games):
    game = config.get_game(games, "blue_game")
    extract.run_pass1(game)
    return game


def test_chunks_are_even():
    batch = {"batch": 1, "grids": [{"cells": [1, 2, 3, 4]}] * 9}
    assert [len(c.grids) for c in plan_chunks(batch, 1, 4)] == [3, 3, 3]
    assert [len(c.grids) for c in plan_chunks(batch, 2)] == [5, 4]       # one moment, split in two
    assert plan_chunks(batch, 1, 4)[0].name == "b001_c00"


def test_whole_pass_runs_in_parallel(game):
    fake = FakeClaude()
    updates = []
    report = run_pass(game, 1, ApiAnalyzer(client=fake.client()), workers=4, grids_per_chunk=2,
                      progress=updates.append)
    assert report.total_chunks == 6 and report.done_chunks == 6 and not report.failed
    assert sorted(report.saved_batches) == [1, 2, 3]
    assert len(analyzer.load_log("blue_game")) == 42
    assert report.usage["requests"] == 6 and report.cost > 0
    assert updates[-1]["done"] == 6 and updates[-1]["stage"] == "analyze1"
    assert pending_grids("blue_game", 1) == 0
    assert len(list(cache_dir("blue_game", 1).glob("*.json"))) == 6


def test_failures_are_isolated_and_resumed(game):
    manifest = analyzer.load_manifest("blue_game", 1)
    batch2 = {c["timestamp"] for g in manifest["batches"][1]["grids"] for c in g["cells"]}

    def fail_batch2(body, n):
        text = body["messages"][0]["content"][-1]["text"]
        return error_response(400, "bad image", "invalid_request_error") if any(s in text for s in batch2) else None

    # A 400 is fatal: the run stops, but finished chunks are kept.
    report = run_pass(game, 1, ApiAnalyzer(client=FakeClaude(behaviors=[fail_batch2]).client()),
                      workers=1, grids_per_chunk=2)
    assert report.fatal and 2 not in report.saved_batches
    saved = set(analyzer.load_progress("blue_game")["pass1"]["done_batches"])
    cached = [p.stem for p in cache_dir("blue_game", 1).glob("*.json")
              if int(p.stem[1:4]) not in saved]

    fake = FakeClaude()
    report = run_pass(game, 1, ApiAnalyzer(client=fake.client()), workers=3, grids_per_chunk=2)
    # Saved batches are skipped, finished chunks come from the cache, only the rest is sent.
    assert report.total_chunks == 2 * (3 - len(saved))
    assert report.cached_chunks == len(cached)
    assert len(fake.requests) == report.total_chunks - len(cached)
    assert analyzer.load_progress("blue_game")["pass1"]["done_batches"] == [1, 2, 3]


def test_one_bad_chunk_does_not_stop_the_rest(game, no_sleep):
    fake = FakeClaude(behaviors=[lambda body, n: error_response(500) if "00:02" in body["messages"][0]["content"][-1]["text"] else None])
    report = run_pass(game, 1, ApiAnalyzer(client=fake.client()), workers=3, grids_per_chunk=2)
    assert len(report.failed) == 1 and sorted(report.saved_batches) == [2, 3]
    assert analyzer.load_progress("blue_game")["pass1"]["done_batches"] == [2, 3]


def test_stop_button(game):
    stop = threading.Event()
    fake = FakeClaude(behaviors=[lambda body, n: time.sleep(0.3)])     # requests take a while
    report = run_pass(game, 1, ApiAnalyzer(client=fake.client()), workers=1, grids_per_chunk=2,
                      progress=lambda update: stop.set() if update["done"] >= 1 else None, stop=stop)
    assert report.stopped and len(fake.requests) < 6
