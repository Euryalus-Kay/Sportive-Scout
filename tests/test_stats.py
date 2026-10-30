from collections import Counter

import pytest

from src import config, report, visualize
from src.aggregate import _collect_events, _pass2_windows, game_stats, in_box, team_profile
from src.insights import _key_player, game_plan, strengths, weaknesses
from src.ui import charts


@pytest.fixture(scope="module")
def sample():
    from src import sample_data
    sample_data.ensure()
    cfg = config.load_config(config.SAMPLE_GAMES_FILE)
    return (cfg, team_profile(cfg, "Riverside FC", config.SAMPLE_LOGS_DIR),
            team_profile(cfg, "Northgate United", config.SAMPLE_LOGS_DIR))


def test_profiles_find_the_planted_patterns(sample):
    _, us, them = sample
    assert us["possession_pct"] > 55 and them["formation_out"] == "4-5-1"
    assert any(f["title"].startswith("Controls possession") for f in strengths(us))
    assert any(f["title"].startswith("Sit deep") for f in weaknesses(them))
    assert us["rates"]["presses_90"] > them["rates"]["presses_90"]
    assert them["timeline"].shape == (19, 4) and them["timeline"].sum() > 0


def test_findings_point_at_their_moments(sample):
    _, us, _ = sample
    shots = next(f for f in strengths(us) if f["title"].startswith("Creates a lot of shots"))
    assert shots["moments"] and shots["moments"][0]["game_id"] == "sample_riverside_vs_lakeview"
    assert shots["moments"][0]["seconds"] is not None


def test_game_plan_links_the_teams(sample):
    _, us, them = sample
    plan = game_plan(us, them)
    assert plan["exploit"] and plan["counter"] and plan["first_15"]
    assert any(m["matches"] for m in plan["exploit"])


def entry(t, source, events=(), half=1):
    return {"timestamp": config.format_time(t), "video_seconds": t, "half": half, "game_minute": t / 60,
            "source": source, "batch": 1, "ball_zone": [6, 2], "ball_xy": None, "events": list(events)}


def test_one_goal_seen_on_many_frames_counts_once():
    game = config._prepare_game({"id": "g"})
    goal = {"type": "shot", "team": "analyzed_team", "outcome": "goal"}
    log = [entry(100, "pass2", [goal]), entry(101, "pass2", [goal]), entry(103, "pass2", [goal]),
           entry(400, "pass2", [goal])]
    goals = [e for e in _collect_events(game, log) if e.get("outcome") == "goal"]
    assert [g["video_seconds"] for g in goals] == [100, 400]


def test_pass2_windows_follow_the_frames_not_batch_numbers():
    log = [entry(t, "pass2") for t in (100, 101, 102, 500, 501)]
    for e in log:
        e["batch"] = 1                          # same number from two different extractions
    assert _pass2_windows(log) == [(100, 102), (500, 501)]


def test_pass1_shots_inside_a_pass2_window_are_replaced():
    game = config._prepare_game({"id": "g"})
    shot = {"type": "shot", "team": "analyzed_team", "outcome": "on_target"}
    log = [entry(96, "pass1", [shot]), entry(95, "pass2"), entry(97, "pass2", [shot]), entry(99, "pass2")]
    shots = [e for e in _collect_events(game, log) if e["type"] == "shot"]
    assert len(shots) == 1 and shots[0]["video_seconds"] == 97


def test_goals_from_games_yaml_are_never_lost(project):
    game = config._prepare_game({"id": "nolog", "goal_times": [{"time": "10:00", "team": "other_team", "position": "CB"}]})
    stats = game_stats(game)
    assert stats["shots"][0]["from_yaml"] and stats["shots"][0]["half"] == 1


def test_small_helpers():
    assert in_box([95, 50]) and not in_box([70, 50]) and not in_box(None)
    assert _key_player(Counter({"10": 20, "9": 5})) == ("10", 20, 80.0)
    assert _key_player(Counter({"10": 3})) == (None, 0, 0)


def test_every_chart_draws_even_without_data(project, sample):
    cfg = config.load_config(config.SAMPLE_GAMES_FILE)
    empty = team_profile(cfg, "Nobody")
    for fig in visualize.team_figures(empty).values():
        assert fig is not None
    _, us, them = sample
    assert visualize.comparison_chart(us, them) and visualize.comparison_chart(empty, empty)
    for fig in (charts.heat_map(us["heat_in"]), charts.shot_map(us["shots_for"]), charts.momentum(us),
                charts.formation("4-3-3", "high"), charts.momentum(empty), charts.shot_map([]),
                charts.shapes_seen(us["shape_out"]), charts.bars({})):
        assert fig.to_dict()


def test_reports(project, sample):
    cfg, us, them = sample
    html = report.html_report(us, them, game_plan(us, them))
    assert html.count("data:image/png;base64") >= 18 and "How to" not in html[:200]
    report.build(cfg, config.SAMPLE_LOGS_DIR, config.REPORTS_DIR)
    for name in ("game_plan.md", "riverside_fc_report.md", "scouting_report.html"):
        assert (config.REPORTS_DIR / name).exists()
