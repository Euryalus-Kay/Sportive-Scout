from collections import Counter

import pytest

from src import config, report, visualize
from src.aggregate import _collect_events, _pass2_windows, game_stats, in_box, retimed, team_profile
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
    assert any(f["label"] == "possession" and f["stat"].endswith("%") for f in strengths(us))
    assert any(f["label"] == "of defending time in a low block" for f in weaknesses(them))
    assert us["rates"]["presses_90"] > them["rates"]["presses_90"]
    assert them["timeline"].shape == (19, 4) and them["timeline"].sum() > 0


def test_findings_point_at_their_moments(sample):
    _, us, _ = sample
    shots = next(f for f in strengths(us) if f["label"] == "shots per 90")
    assert shots["moments"] and shots["moments"][0]["game_id"] == "sample_riverside_vs_lakeview"
    assert shots["moments"][0]["seconds"] is not None


def test_game_plan_links_the_teams(sample):
    _, us, them = sample
    plan = game_plan(us, them)
    assert plan["exploit"] and plan["counter"] and plan["first_15"]
    linked = [m for m in plan["exploit"] if m["matches"]]
    assert linked and linked[0]["match_items"][0]["title"] == linked[0]["matches"][0]


def test_insights_are_plain_facts(sample):
    _, us, them = sample
    for f in strengths(us) + weaknesses(us) + strengths(them) + weaknesses(them):
        assert f["stat"] and f["label"] and f["basis"] and f["title"] == f"{f['stat']} {f['label']}"
        text = f"{f['stat']} {f['label']} {f['basis']}"
        assert "—" not in text and not text.rstrip().endswith("!")


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


def test_minutes_follow_games_yaml_not_the_stored_log(project):
    game = config._prepare_game({"id": "g", "kickoff_time": "00:00", "second_half_start": "50:00", "half_length": 40})
    log = [dict(entry(51 * 60, "pass1", [{"type": "shot", "team": "analyzed_team", "outcome": "goal"}], half=2),
                game_minute=46.0)]               # stored with the old 45-minute rule
    goal = _collect_events(game, retimed(game, log))[0]
    assert goal["game_minute"] == pytest.approx(41.0) and not goal["late"]


def test_a_film_with_both_teams_counts_for_both(project):
    from src.analyzer import log_path, write_json
    cfg = {"matchup": {"our_team": "A", "opponent": "B"}, "games": [config._prepare_game(
        {"id": "ab", "file": "ab.mp4", "analyzed_team_name": "A", "other_team_name": "B",
         "final_score": "2-1", "opponent_strength": "weaker", "kickoff_time": "00:00"})]}
    shot = {"type": "shot", "team": "other_team", "outcome": "on_target", "xy": [90, 20]}
    first = dict(entry(60, "pass1", [shot]), view="wide", possession="analyzed_team", confidence=0.8,
                 ball_zone=[6, 1], analyzed_team_shape="4-4-2", other_team_shape="3-5-2", players=["10"],
                 analyzed_team_block="high", other_team_block="low")
    config.LOGS_DIR.mkdir(exist_ok=True)
    write_json(log_path("ab"), [first])
    a, b = team_profile(cfg, "A"), team_profile(cfg, "B")
    assert a["possession_pct"] == 100 and b["possession_pct"] == 0
    assert b["heat_out"][3, 0] == 1                      # A's ball at B's back-right corner
    seen = [x for x in b["shots_for"] if not x.get("from_score")]
    assert len(seen) == 1 and seen[0]["xy"] == [10, 80]
    assert len(a["goals_for"]) == 2 and len(b["goals_for"]) == 1    # the 2-1 score, goals not caught on film
    assert b["shape_out"]["3-5-2"] == 1 and not b["players"]
    assert b["games"][0]["final_score"] == "1-2" and b["games"][0]["opponent_strength"] == "stronger"
    cfg["games"].append(dict(cfg["games"][0], id="ba", analyzed_team_name="B", other_team_name="A"))
    assert len(team_profile(cfg, "B")["games"]) == 1     # same video analyzed for B: no double count
