import os

import pytest

from src import config


def test_parse_and_format_time():
    assert config.parse_time("23:10") == 1390
    assert config.parse_time("1:02:03") == 3723
    assert config.parse_time(75) == 75.0
    assert config.parse_time("") is None and config.parse_time(None) is None
    assert config.format_time(3723) == "62:03"
    assert config.format_time(59.6) == "01:00"


def test_bad_time_has_a_clear_message():
    with pytest.raises(ValueError, match="mm:ss"):
        config.parse_time("12m30")


def test_halves_minutes_and_directions():
    game = config._prepare_game({"id": "g", "kickoff_time": "00:10", "first_half_end": "47:00",
                                 "second_half_start": "50:00", "attacking_direction": "left"})
    assert config.half_for(game, 5) == 0
    assert config.half_for(game, 600) == 1
    assert config.half_for(game, 48 * 60) == 0        # halftime
    assert config.half_for(game, 51 * 60) == 2
    assert config.game_minute(game, 70) == pytest.approx(1.0)
    assert config.game_minute(game, 52 * 60) == pytest.approx(47.0)
    assert config.attacking_direction(game, 1) == "left"
    assert config.attacking_direction(game, 2) == "right"


def test_high_school_halves_are_40_minutes():
    game = config._prepare_game({"id": "g", "kickoff_time": "05:00", "first_half_end": "47:00",
                                 "second_half_start": "57:00", "half_length": "40"})
    assert game["half_length"] == 40
    assert config.game_minute(game, 59 * 60) == pytest.approx(42.0)      # 2 min into the 2nd half
    assert config.is_late(game, 66) and not config.is_late(game, 64)      # last 15 of 80
    assert config.is_late(config._prepare_game({"id": "g"}), 76)          # last 15 of 90
    ended = config._prepare_game({"id": "g", "kickoff_time": "05:00", "second_half_start": "57:00",
                                  "game_end": "1:40:00"})
    assert config.half_for(ended, 99 * 60) == 2 and config.half_for(ended, 101 * 60) == 0
    bad = config._prepare_game({"id": "g", "file": "a.mp4", "analyzed_team_name": "A", "half_length": 90})
    assert any("half_length" in p for p in config._game_problems(bad, {"our_team": "A", "opponent": "B"}))


def test_sample_config_is_valid():
    assert config.validate_config(config.load_config(config.SAMPLE_GAMES_FILE)) == []


def test_validate_config_explains_problems():
    cfg = {"matchup": {"our_team": "A", "opponent": "B"}, "games": [config._prepare_game({
        "id": "bad game", "file": "", "team_analyzed": "us", "analyzed_team_name": "C",
        "attacking_direction": "up", "opponent_strength": "much better",
        "kickoff_time": "10:00", "second_half_start": "05:00",
        "goal_times": [{"team": "them"}]})]}
    text = "\n".join(config.validate_config(cfg))
    for expected in ["can't contain spaces", "file is empty", "must match our_team",
                     "attacking_direction", "opponent_strength", "second_half_start must be after",
                     "has no time", "team must be analyzed_team"]:
        assert expected in text


def test_duplicate_ids_and_missing_teams():
    game = {"id": "g", "file": "x.mp4", "analyzed_team_name": "A"}
    cfg = {"matchup": {"our_team": "A"}, "games": [config._prepare_game(game), config._prepare_game(game)]}
    text = "\n".join(config.validate_config(cfg))
    assert "two different team names" in text and "used more than once" in text


def test_raw_round_trip(tmp_path):
    data = {"matchup": {"our_team": "A", "opponent": "B"}, "games": [{"id": "g", "kickoff_time": "00:05"}]}
    config.save_raw(data, tmp_path / "games.yaml")
    assert config.load_raw(tmp_path / "games.yaml") == data
    assert config.load_raw(tmp_path / "missing.yaml") == {}


def test_load_env_never_overwrites(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nexport SCOUT_TEST_A='one'\nSCOUT_TEST_B=two\nnot a line\n")
    monkeypatch.setenv("SCOUT_TEST_B", "already set")
    monkeypatch.delenv("SCOUT_TEST_A", raising=False)
    config.load_env(env)
    assert os.environ["SCOUT_TEST_A"] == "one"
    assert os.environ["SCOUT_TEST_B"] == "already set"
    monkeypatch.delenv("SCOUT_TEST_A")
