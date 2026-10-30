"""Sportive Scout: the local interface.

Run with:  streamlit run app.py

The pages live in src/ui/pages/. The look (colors, cards) is in src/ui/theme.py
and the interactive charts in src/ui/charts.py.
"""
import streamlit as st

from src import config, jobs
from src.api_analyzer import api_key_available
from src.pack import open_pack
from src.ui import theme
from src.ui.common import has_real_logs, use_sample

REPO = "https://github.com/Euryalus-Kay/Sportive-Scout"

st.set_page_config(page_title="Sportive Scout", page_icon=":material/sports_soccer:", layout="wide")
theme.apply()

pages = {
    "Scouting": [
        st.Page("src/ui/pages/overview.py", title="Overview", icon=":material/dashboard:", default=True),
        st.Page("src/ui/pages/us.py", title="Your team", icon=":material/shield:"),
        st.Page("src/ui/pages/them.py", title="Opponent", icon=":material/target:"),
        st.Page("src/ui/pages/matchup.py", title="Matchup", icon=":material/compare_arrows:"),
        st.Page("src/ui/pages/moments.py", title="Moments", icon=":material/movie:"),
    ],
    "Workflow": [
        st.Page("src/ui/pages/analyze.py", title="Analyze film", icon=":material/add_a_photo:"),
        st.Page("src/ui/pages/guide.py", title="Guide", icon=":material/help:"),
    ],
}
page = st.navigation(pages, position="top")


def open_analysis():
    """Website app: open an analysis pack (games.yaml + logs). It is read in this browser tab only."""
    if has_real_logs():
        st.caption("Your analysis is open in this tab only. Nothing was uploaded.")
    else:
        st.caption(f"Demo with made-up teams. Open your own analysis below, or run the app on your "
                   f"computer to analyze film ([how]({REPO}#setup-once)).")
    pack = st.file_uploader("Open your analysis", type="zip", key="pack",
                            help="The .zip made by `python -m src.pack`. It never leaves this browser tab.")
    if pack and st.session_state.get("pack_opened") != (pack.name, pack.size):
        try:
            open_pack(pack.getvalue())
        except (ValueError, KeyError, OSError) as err:
            st.error(f"Couldn't open it: {err}")
            return
        st.session_state.pack_opened = (pack.name, pack.size)
        st.session_state.use_sample = False
        st.rerun()


with st.sidebar:
    st.html('<div style="font-weight:700;font-size:1.05rem;letter-spacing:-.01em">Sportive Scout</div>'
            '<div class="pm-label" style="margin-top:2px">Soccer film scouting</div>')
    if config.IN_BROWSER:
        open_analysis()
    if not config.IN_BROWSER or has_real_logs():
        sample = use_sample()
        choice = st.radio("Data", ["My games", "Demo data (fake teams)"], index=1 if sample else 0,
                          help="The demo uses made-up teams so you can try the app before adding film.")
        if choice.startswith("Demo") != sample:
            st.session_state.use_sample = choice.startswith("Demo")
            st.rerun()
        if not sample and not has_real_logs():
            st.caption("Nothing analyzed yet. Start on Analyze film.")
    if not config.IN_BROWSER:
        st.divider()
        theme.heading("Status")
        job = jobs.current()
        theme.status([("Claude API key found" if api_key_available() else "No API key: Claude Code mode",
                       theme.GOOD if api_key_available() else "#9ca3af"),
                      ("games.yaml ready" if config.GAMES_FILE.exists() else "No games.yaml yet",
                       theme.GOOD if config.GAMES_FILE.exists() else "#9ca3af")]
                     + ([(f"Analyzing {job.game or '...'}", theme.US)] if job and job.running else []))
    st.caption("Pitches show each team attacking left to right, their left touchline on top.")

page.run()
