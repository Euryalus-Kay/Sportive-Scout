"""Sportive Scout: the local interface.

Run with:  streamlit run app.py

The pages live in src/ui/pages/. The look (colors, cards) is in src/ui/theme.py
and the interactive charts in src/ui/charts.py.
"""
import streamlit as st

from src import config, jobs
from src.api_analyzer import api_key_available
from src.ui import theme
from src.ui.common import has_real_logs, use_sample

st.set_page_config(page_title="Sportive Scout", page_icon="⚽", layout="wide")
theme.apply()

pages = {
    "Scouting": [
        st.Page("src/ui/pages/overview.py", title="Overview", icon=":material/dashboard:", default=True),
        st.Page("src/ui/pages/us.py", title="Your team", icon=":material/shield:"),
        st.Page("src/ui/pages/them.py", title="Opponent", icon=":material/target:"),
        st.Page("src/ui/pages/plan.py", title="Game plan", icon=":material/strategy:"),
        st.Page("src/ui/pages/moments.py", title="Moments", icon=":material/movie:"),
    ],
    "Workflow": [
        st.Page("src/ui/pages/analyze.py", title="Analyze film", icon=":material/add_a_photo:"),
        st.Page("src/ui/pages/guide.py", title="Guide", icon=":material/help:"),
    ],
}
page = st.navigation(pages, position="top")

with st.sidebar:
    st.markdown("### ⚽ Sportive Scout")
    st.caption("Soccer film scouting: heat maps, shapes, shots, strengths and a game plan.")
    sample = use_sample()
    choice = st.radio("Data", ["My games", "Demo data (fake teams)"], index=1 if sample else 0,
                      help="The demo shows made-up teams so you can try everything before adding film.")
    if choice.startswith("Demo") != sample:
        st.session_state.use_sample = choice.startswith("Demo")
        st.rerun()
    if not sample and not has_real_logs():
        st.caption("Nothing analyzed yet. Start on **Analyze film**.")
    st.divider()
    theme.label("Status")
    job = jobs.current()
    theme.status([("Claude API key found" if api_key_available() else "No API key: Claude Code mode",
                   theme.GOOD if api_key_available() else "#9ca3af"),
                  ("games.yaml ready" if config.GAMES_FILE.exists() else "No games.yaml yet",
                   theme.GOOD if config.GAMES_FILE.exists() else "#9ca3af")]
                 + ([(f"Analyzing {job.game or '...'}", theme.US)] if job and job.running else []))
    st.caption("Pitches are drawn with each team attacking left → right, their left touchline on top.")

page.run()
