"""Matchup: their numbers lined up against ours. Facts only, no advice."""
import streamlit as st

from src import config
from src.insights import game_plan, set_piece_numbers, setup
from src.ui import theme
from src.ui.common import load, needs_setup, no_logs, source_paths

data = load()
if data is None:
    needs_setup()
    st.stop()
cfg, us, them, sample = data
plan = game_plan(us, them)

theme.page_title("Matchup" + (" · demo data" if sample else ""), f"{us['team']} vs {them['team']}")
theme.chips([(note, "") for note in plan["context"]])
if not (us["frames_logged"] or them["frames_logged"]):
    no_logs(sample)
    st.stop()


def linked(items):
    """(their finding, [our related findings]) for every finding that shares a tag with ours."""
    return [(m["item"], m["match_items"]) for m in items if m["match_items"]]


st.space("small")
against_us, for_us = linked(plan["counter"]), linked(plan["exploit"])
with theme.card():
    theme.heading("Where it lines up", "Their numbers next to ours on the same thing")
    if not (against_us or for_us):
        st.caption("No overlaps between the two teams' patterns yet.")
    for title, rows, color in ((f"{them['team']} strength · {us['team']} weakness", against_us, theme.BAD),
                               (f"{them['team']} weakness · {us['team']} strength", for_us, theme.GOOD)):
        if rows:
            st.html(f'<div class="pm-label" style="margin-top:10px">{theme.esc(title)}</div>')
            theme.pair_rows(rows, theme.THEM, color)

left, right = st.columns(2, gap="medium")
for col, title, items in ((left, "Strengths", [m["item"] for m in plan["counter"]]),
                          (right, "Weaknesses", [m["item"] for m in plan["exploit"]])):
    with col, theme.card():
        theme.heading(them["team"], title)
        if not items:
            st.caption("Nothing clear enough yet.")
        for f in items:
            theme.insight_row(f, theme.THEM)

left, right = st.columns(2, gap="medium")
with left, theme.card():
    theme.heading(them["team"], "Usual setup")
    theme.facts(setup(them))
with right, theme.card():
    theme.heading(us["team"], "Usual setup")
    theme.facts(setup(us))

with theme.card():
    theme.heading("Set pieces", "Logged in the analyzed film")
    ours, theirs = set_piece_numbers(us), set_piece_numbers(them)
    shown = lambda p, n: str(n) if p["frames_logged"] else "–"
    st.dataframe([{"": name, us["team"]: shown(us, ours[name]), them["team"]: shown(them, theirs[name])}
                  for name in ours], hide_index=True, width="stretch")

with theme.card():
    theme.heading("Share", "A printable page with every chart")
    games_file, logs_dir, reports_dir = source_paths(sample)
    cols = st.columns([1, 1, 2])
    report_key = f"html_report_{sample}_{us['frames_logged']}_{them['frames_logged']}"
    if report_key in st.session_state:
        cols[0].download_button("Download report", st.session_state[report_key], file_name="scouting_report.html",
                                mime="text/html", icon=":material/download:", width="stretch")
    elif cols[0].button("Build report", icon=":material/description:", width="stretch"):
        with st.spinner("Drawing every chart..."):
            from src.report import html_report      # loads matplotlib only when asked
            st.session_state[report_key] = html_report(us, them, plan)
        st.rerun()
    if not config.IN_BROWSER and cols[1].button("Save to reports folder", icon=":material/save:", width="stretch"):
        reports_dir.mkdir(parents=True, exist_ok=True)
        with st.spinner("Drawing every chart..."):
            from src.report import build
            build(config.load_config(games_file), logs_dir, reports_dir)
        st.success(f"Saved to {reports_dir.relative_to(config.ROOT)}/")
