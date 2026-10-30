"""Game plan: how to beat the opponent, what to fix, set pieces, the first 15 minutes."""
import streamlit as st

from src import config
from src.insights import game_plan
from src.report import build, game_plan_markdown, html_report
from src.ui import theme
from src.ui.common import load, needs_setup, no_logs, source_paths

data = load()
if data is None:
    needs_setup()
    st.stop()
cfg, us, them, sample = data
plan = game_plan(us, them)

theme.label("Game plan" + (" · demo data" if sample else ""))
st.markdown(f"<div class='ss-team'>How to play {theme.esc(them['team'])}</div>", unsafe_allow_html=True)
if plan["context"]:
    st.html("<div class='ss-chips'>" + "".join(f"<span class='ss-chip'>{theme.esc(n)}</span>"
                                               for n in plan["context"]) + "</div>")
if not (us["frames_logged"] or them["frames_logged"]):
    no_logs(sample)
    st.stop()

left, right = st.columns(2, gap="medium")
with left, theme.card():
    theme.label("Attack them")
    st.markdown("**Their weaknesses, and how to use them**")
    if not plan["exploit"]:
        st.caption("No clear weaknesses yet; analyze more of their film.")
    for m in plan["exploit"]:
        theme.finding_card(m["item"], theme.GOOD, "How",
                           "Fits our strength: " + "; ".join(m["matches"]) if m["matches"] else "")
with right, theme.card():
    theme.label("Stop them")
    st.markdown("**Their strengths, and how to stop them**")
    if not plan["counter"]:
        st.caption("No clear strengths yet; analyze more of their film.")
    for m in plan["counter"]:
        theme.finding_card(m["item"], theme.THEM, "Stop it",
                           "Danger, this hits our weakness: " + "; ".join(m["matches"]) if m["matches"] else "",
                           theme.BAD)

if plan["fix"]:
    with theme.card():
        theme.label("Training this week")
        st.markdown("**Our weaknesses they could target**")
        for w in plan["fix"]:
            theme.finding_card(w, theme.BAD, "How they could use it")

left, right = st.columns(2, gap="medium")
with left, theme.card():
    theme.label("Set pieces")
    for note in plan["set_pieces"]:
        st.markdown(f"- {note}")
with right, theme.card():
    theme.label("First 10-15 minutes")
    st.markdown("**Check these early and adjust**")
    for i, check in enumerate(plan["first_15"]):
        st.checkbox(check, key=f"check_{i}")

with theme.card():
    theme.label("Share it")
    games_file, logs_dir, reports_dir = source_paths(sample)
    cols = st.columns(3)
    report_key = f"html_report_{sample}_{us['frames_logged']}_{them['frames_logged']}"
    if report_key in st.session_state:
        cols[0].download_button("Download printable report", st.session_state[report_key],
                                file_name="scouting_report.html", mime="text/html", icon=":material/print:",
                                width="stretch", help="One file with every chart. Open it and print to PDF.")
    elif cols[0].button("Build printable report", icon=":material/print:", width="stretch",
                        help="One HTML file with every chart, to print or send to coaches."):
        with st.spinner("Drawing every chart..."):
            st.session_state[report_key] = html_report(us, them, plan)
        st.rerun()
    cols[1].download_button("Game plan (Markdown)",
                            game_plan_markdown(us, them, plan, reports_dir / "images", reports_dir),
                            file_name="game_plan.md", icon=":material/description:", width="stretch")
    if cols[2].button("Save all reports to the reports folder", icon=":material/save:", width="stretch"):
        reports_dir.mkdir(parents=True, exist_ok=True)
        with st.spinner("Drawing every chart..."):
            build(config.load_config(games_file), logs_dir, reports_dir)
        st.success(f"Saved to {reports_dir.relative_to(config.ROOT)}/")
