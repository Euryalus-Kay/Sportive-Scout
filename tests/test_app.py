"""Every page of the app renders without errors, on demo data and on an empty setup."""
import pytest
from streamlit.testing.v1 import AppTest

from src import config

PAGES = ["overview", "us", "them", "plan", "moments", "analyze", "guide"]


def open_page(page, sample=True):
    at = AppTest.from_file(str(config.ROOT / "app.py"), default_timeout=120)
    at.session_state["use_sample"] = sample
    at.run()
    at.switch_page(f"src/ui/pages/{page}.py")
    at.run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_demo_pages_render(page):
    at = open_page(page)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_team_page_views():
    at = open_page("them")
    for view in ["Attacking", "Defending", "Shape", "Players", "Overview"]:
        at.segmented_control(key="view_them").set_value(view).run()
        assert not at.exception, (view, [e.value for e in at.exception])
    assert [m.label for m in at.metric][:3] == ["Possession", "Shots", "Goals"]


def test_moments_filters():
    at = open_page("moments")
    at.multiselect(key="m_kinds").set_value(["Turnovers"]).run()
    at.segmented_control(key="m_half").set_value("2nd").run()
    assert not at.exception


@pytest.mark.parametrize("page", PAGES)
def test_pages_before_any_setup(page, project):
    at = open_page(page, sample=False)
    assert not at.exception, [e.value for e in at.exception]


def test_matchup_form_saves_games_yaml(project):
    at = open_page("analyze", sample=False)
    at.text_input[0].set_value("Lab")
    at.text_input[1].set_value("Parker")
    at.button[0].click().run()
    assert config.load_raw()["matchup"] == {"our_team": "Lab", "opponent": "Parker"}
