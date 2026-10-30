from src import analyzer, config, run
from src.api_analyzer import ApiAnalyzer
from src.aggregate import team_profile
from tests.fake_api import FakeClaude


def test_whole_game_end_to_end_and_resume(games):
    game = config.get_game(games, "blue_game")
    fake = FakeClaude(shots_every=10)
    events, asked = [], []
    opts = run.Options(workers=4, grids_per_chunk=2)

    def confirm(cost, grids):
        asked.append((cost, grids))
        return True

    summary = run.analyze_game(game, opts, events.append, confirm=confirm,
                               analyzer=ApiAnalyzer(client=fake.client()))
    assert not summary["failed"] and summary["cost"] > 0
    assert asked and asked[0][1] == 11                                  # 11 grids to pay for
    stages = [e["stage"] for e in events]
    assert stages.index("extract1") < stages.index("analyze1") < stages.index("extract2") < stages.index("analyze2")
    progress = analyzer.load_progress("blue_game")
    assert progress["pass1"]["done_batches"] == [1, 2, 3]
    assert progress["pass2"]["done_batches"]                           # key moments were analyzed
    log = analyzer.load_log("blue_game")
    assert {e["source"] for e in log} == {"pass1", "pass2"}
    assert run.pass1_ready(game) and run.pass2_ready(game)

    profile = team_profile(games, "Blue")
    assert profile["shots_for"] and profile["possession_pct"] == 100
    assert any(g.get("from_yaml") or g.get("outcome") == "goal" for g in profile["goals_for"])

    # Running again changes nothing and sends nothing.
    before = len(fake.requests)
    again = run.analyze_game(game, opts, analyzer=ApiAnalyzer(client=fake.client()))
    assert len(fake.requests) == before and again["cost"] == 0

    assert run.build_reports(games)
    assert (config.REPORTS_DIR / "game_plan.md").exists()
    assert (config.REPORTS_DIR / "blue_report.md").exists()


def test_declining_the_cost_stops_before_spending(games):
    game = config.get_game(games, "red_game")
    fake = FakeClaude()
    summary = run.analyze_game(game, run.Options(), confirm=lambda cost, grids: False,
                               analyzer=ApiAnalyzer(client=fake.client()))
    assert summary["stopped"] and not fake.requests


def test_estimate_before_extracting(games, capsys):
    run.print_estimate(games["games"], run.Options())
    out = capsys.readouterr().out
    assert "blue_game: 44 frames left" in out and "Total with" in out
