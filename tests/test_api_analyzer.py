import json
from types import SimpleNamespace

import pytest

from src import api_analyzer as api
from src import config, extract
from src.analyzer import AnalysisError, FatalAnalysisError
from tests.fake_api import FakeClaude, error_response, frame_for, stream_response


@pytest.fixture
def batch(games):
    game = config.get_game(games, "blue_game")
    manifest = extract.run_pass1(game)
    return game, {"batch": 1, "grids": manifest["batches"][0]["grids"][:2]}


def walk(schema):
    yield schema
    for value in schema.values():
        if isinstance(value, dict):
            yield from walk(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from walk(item)


def test_schema_follows_structured_output_rules():
    for node in walk(api.RESPONSE_SCHEMA):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert sorted(node["required"]) == sorted(node["properties"])
        assert not {"minimum", "maximum", "minLength", "maxLength", "pattern"} & set(node)


def test_request_layout(batch):
    game, b = batch
    req = api.build_request(game, 1, b, "claude-opus-5-5", "low")
    assert req["model"] == "claude-opus-5-5"
    assert req["output_config"]["effort"] == "low"
    assert req["output_config"]["format"]["schema"] is api.RESPONSE_SCHEMA
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    content = req["messages"][0]["content"]
    assert content[0]["cache_control"] == {"type": "ephemeral"}       # game info is cached too
    assert "blue shirts" in content[0]["text"] and "RIGHT" in content[0]["text"]
    assert sum(block["type"] == "image" for block in content) == 2
    assert content[-1]["text"].startswith("Log these 8 frames, in this order: 00:02, 00:06")
    pass2 = api.build_request(game, 2, b)["messages"][0]["content"]
    assert pass2[1]["text"] == api.PASS2_NOTE


def message(text, stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])


def test_parse_frames_checks_the_answer():
    cells = [{"timestamp": "00:02"}, {"timestamp": "00:06"}, {"timestamp": "00:10"}, {"timestamp": "00:14"}]
    frames = [frame_for("0:02"), frame_for("00:06"), frame_for("00:06"), frame_for("00:10"), frame_for("99:00")]
    entries = api.parse_frames(message(json.dumps({"frames": frames})), cells)
    assert [e["timestamp"] for e in entries] == ["00:02", "00:06", "00:10"]
    with pytest.raises(AnalysisError, match="declined"):
        api.parse_frames(message("", "refusal"), cells)
    with pytest.raises(AnalysisError, match="JSON"):
        api.parse_frames(message("{not json"), cells)
    with pytest.raises(AnalysisError, match="only 1 of 4"):
        api.parse_frames(message(json.dumps({"frames": frames[:1]})), cells)


def test_raw_entries_are_cleaned_up():
    frame = frame_for("00:02", shot=True)
    frame.update(ball_screen={"col": 9, "row": 0}, ball_xy_screen={"x": 120, "y": -5},
                 confidence=1.7, players=["#10", " ", "7"])
    raw = api.to_raw_entry(frame)
    assert raw["ball_screen"] == [6, 1] and raw["ball_xy_screen"] == [100, 0]
    assert raw["confidence"] == 1.0 and raw["players"] == ["10", "7"]
    assert raw["events"][0] == {"type": "shot", "team": "analyzed_team", "outcome": "on_target",
                                "position": "ST", "build_up": "wide", "xy_screen": [88.0, 45.0]}


def test_analyze_through_the_real_sdk(batch):
    game, b = batch
    fake = FakeClaude()
    entries, usage = api.ApiAnalyzer(client=fake.client()).analyze(game, 1, b)
    assert len(entries) == 8 and entries[0]["timestamp"] == "00:02"
    assert usage["requests"] == 1 and usage["input_tokens"] == 9000 and usage["output_tokens"] == 2000
    assert usage["cost"] == pytest.approx((9000 * 4 + 2000 * 20 + 1700 * 0.2) / 1e6)
    body, headers = fake.requests[0], fake.headers[0]
    assert body["fallbacks"] == "default" and api.FALLBACK_BETA in headers["anthropic-beta"]
    assert body["stream"] is True and body["max_tokens"] == api.MAX_TOKENS
    image = next(c for c in body["messages"][0]["content"] if c["type"] == "image")
    assert image["source"]["media_type"] == "image/jpeg" and len(image["source"]["data"]) > 1000


def test_bad_key_stops_everything(batch):
    game, b = batch
    fake = FakeClaude(behaviors=[lambda body, n: error_response(401, kind="authentication_error")])
    with pytest.raises(FatalAnalysisError, match="API key"):
        api.ApiAnalyzer(client=fake.client()).analyze(game, 1, b)


def test_temporary_errors_and_bad_answers_are_retried(batch, no_sleep):
    game, b = batch
    flaky = {1: error_response(529, kind="overloaded_error"), 2: stream_response("{oops")}
    fake = FakeClaude(behaviors=[lambda body, n: flaky.get(n)])
    entries, usage = api.ApiAnalyzer(client=fake.client()).analyze(game, 1, b)
    assert len(entries) == 8 and len(fake.requests) == 3 and usage["requests"] == 2


def test_gives_up_after_the_retries(batch, no_sleep):
    game, b = batch
    fake = FakeClaude(behaviors=[lambda body, n: stream_response("{oops")])
    with pytest.raises(AnalysisError, match="no usable answer after 3 tries"):
        api.ApiAnalyzer(client=fake.client()).analyze(game, 1, b)


def test_too_long_answers_split_the_batch(batch):
    game, b = batch
    fake = FakeClaude(behaviors=[lambda body, n: stream_response("{", "max_tokens") if n == 1 else None])
    entries, usage = api.ApiAnalyzer(client=fake.client()).analyze(game, 1, b)
    assert len(entries) == 8 and len(fake.requests) == 3       # 1 cut off, then 2 halves
    assert sum(c["type"] == "image" for c in fake.requests[1]["messages"][0]["content"]) == 1


def test_cost_estimate_scales():
    small, big = api.estimate_cost(10), api.estimate_cost(100)
    assert 0 < small < big
    assert api.estimate_cost(100, "claude-haiku-5-5") < api.estimate_cost(100, "claude-opus-5-5")
