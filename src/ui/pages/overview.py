"""Overview: the matchup at a glance."""
import streamlit as st

from src.insights import strengths, weaknesses
from src.ui import charts, theme
from src.ui.common import hero, load, needs_setup, no_logs

data = load()
if data is None:
    needs_setup()
    st.stop()
cfg, us, them, sample = data
hero(cfg, us, them, sample)
if not (us["frames_logged"] or them["frames_logged"]):
    no_logs(sample)
    st.stop()

r, s = us["rates"], them["rates"]
goals = lambda p, key: len(p[key]) * p["per90"]
st.space("small")
theme.duel_tiles([
    ("Possession", r["possession"], s["possession"], "{:.0f}%"),
    ("Goals per 90", goals(us, "goals_for"), goals(them, "goals_for"), "{:.1f}"),
    ("Shots per 90", r["shots_90"], s["shots_90"], "{:.1f}"),
    ("Shots conceded per 90", r["shots_against_90"], s["shots_against_90"], "{:.1f}"),
])
st.space("small")

left, right = st.columns([1, 1], gap="medium")
with left, theme.card():
    theme.heading("Head to head", "Per 90 minutes, from each team's own games")
    theme.legend(us["team"], them["team"])
    theme.compare_rows([
        ("Goals conceded per 90", goals(us, "goals_against"), goals(them, "goals_against"), "{:.1f}", False),
        ("Shots on target", r["on_target_pct"], s["on_target_pct"], "{:.0f}%", True),
        ("Shots from inside the box", r["box_shots_pct"], s["box_shots_pct"], "{:.0f}%", True),
        ("Possession in the final third", r["final_third_pct"], s["final_third_pct"], "{:.0f}%", True),
        ("Own-half turnovers per 90", r["turnovers_own_half_90"], s["turnovers_own_half_90"], "{:.1f}", False),
        ("Presses per 90", r["presses_90"], s["presses_90"], "{:.1f}", None),
        ("Crosses per 90", r["crosses_90"], s["crosses_90"], "{:.1f}", None),
        ("Long balls per 90", r["long_balls_90"], s["long_balls_90"], "{:.1f}", None),
        ("High block", r["high_block_pct"], s["high_block_pct"], "{:.0f}%", None),
        ("Low block", r["low_block_pct"], s["low_block_pct"], "{:.0f}%", None),
    ])

with right, theme.card():
    theme.heading(them["team"], "What stands out")
    picks = strengths(them)[:2] + weaknesses(them)[:2]
    if not picks:
        st.caption("Nothing clear enough yet.")
    cols = st.columns(2, gap="small")
    for i, f in enumerate(picks):
        with cols[i % 2]:
            theme.insight(f, theme.THEM)
    st.page_link("src/ui/pages/them.py", label=f"All {them['team']} insights", icon=":material/arrow_forward:")

left, right = st.columns(2, gap="medium")
with left, theme.card():
    theme.heading(them["team"], "Possession by 5 minutes")
    st.plotly_chart(charts.momentum(them, theme.THEM), config=charts.CONFIG, width="stretch")
with right, theme.card():
    theme.heading(them["team"], "Shape without the ball")
    st.plotly_chart(charts.formation(them["formation_out"], them["block_out_main"], color=theme.THEM, height=300),
                    config=charts.CONFIG, width="stretch")

with theme.card():
    theme.heading("Goals", "Every goal in the analyzed film")
    rows = [{"Team": p["team"], "Minute": f"{int(g['game_minute']) + 1}'" if g.get("game_minute") is not None else "?",
             "Scorer": g.get("position") or "unknown", "Build-up": (g.get("build_up") or "unknown").replace("_", " "),
             "Film time": g.get("timestamp") or "?"}
            for p in (us, them) for g in p["goals_for"]]
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.caption("No goals logged yet.")
