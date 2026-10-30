"""Overview: the matchup at a glance (head to head, the plan in short, key moments)."""
import streamlit as st

from src.insights import game_plan
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

plan = game_plan(us, them)
left, right = st.columns([1.05, 1], gap="medium")

with left, theme.card():
    theme.label("Head to head")
    st.markdown("**How the two teams play**")
    r, s = us["rates"], them["rates"]
    goals = lambda p, key: len(p[key]) * p["per90"]
    theme.compare_rows(us["team"], them["team"], [
        ("Possession", r["possession"], s["possession"], "{:.0f}%", True),
        ("Goals per 90", goals(us, "goals_for"), goals(them, "goals_for"), "{:.1f}", True),
        ("Goals conceded per 90", goals(us, "goals_against"), goals(them, "goals_against"), "{:.1f}", False),
        ("Shots per 90", r["shots_90"], s["shots_90"], "{:.1f}", True),
        ("Shots conceded per 90", r["shots_against_90"], s["shots_against_90"], "{:.1f}", False),
        ("Shots on target", r["on_target_pct"], s["on_target_pct"], "{:.0f}%", True),
        ("Shots from inside the box", r["box_shots_pct"], s["box_shots_pct"], "{:.0f}%", True),
        ("Possession in the final third", r["final_third_pct"], s["final_third_pct"], "{:.0f}%", True),
        ("Turnovers in own half per 90", r["turnovers_own_half_90"], s["turnovers_own_half_90"], "{:.1f}", False),
        ("Presses per 90", r["presses_90"], s["presses_90"], "{:.1f}", None),
        ("Crosses per 90", r["crosses_90"], s["crosses_90"], "{:.1f}", None),
        ("Long balls per 90", r["long_balls_90"], s["long_balls_90"], "{:.1f}", None),
        ("Defends with a high block", r["high_block_pct"], s["high_block_pct"], "{:.0f}%", None),
    ])
    st.caption("Each team's numbers come from its own games, scaled to 90 minutes, so this compares "
               "styles rather than one match. Highlighted = better on that measure.")

with right:
    with theme.card():
        theme.label("The plan in short")
        st.markdown(f"**How to play {them['team']}**")
        sections = [("Hurt them here", plan["exploit"][:2], theme.GOOD, "How"),
                    ("Watch out for", plan["counter"][:2], theme.THEM, "Stop it")]
        for title, items, tone, action in sections:
            st.markdown(f"<div class='ss-label' style='margin-top:8px'>{title}</div>", unsafe_allow_html=True)
            if not items:
                st.caption("Nothing clear enough yet.")
            for m in items:
                theme.finding_card(m["item"], tone, action)
        if plan["fix"]:
            st.markdown("<div class='ss-label'>Fix this week</div>", unsafe_allow_html=True)
            st.html("".join(f"<div class='ss-sub' style='color:#374151'>&bull; {theme.esc(w['title'])}</div>"
                            for w in plan["fix"][:3]))
        st.page_link("src/ui/pages/plan.py", label="Open the full game plan", icon=":material/arrow_forward:")

left, right = st.columns(2, gap="medium")
with left, theme.card():
    theme.label(f"{them['team']} · momentum")
    st.markdown("**Who had the ball, 5 minutes at a time**")
    st.plotly_chart(charts.momentum(them, theme.THEM), config=charts.CONFIG, width="stretch")
with right, theme.card():
    theme.label(f"{them['team']} · shape without the ball")
    st.markdown("**How they defend**")
    st.plotly_chart(charts.formation(them["formation_out"], them["block_out_main"], color=theme.THEM, height=330),
                    config=charts.CONFIG, width="stretch")

with theme.card():
    theme.label("Goals")
    st.markdown("**Every goal in the analyzed film**")
    rows = [{"Team": p["team"], "Scored by": g.get("position") or "unknown",
             "How": (g.get("build_up") or "unknown").replace("_", " "),
             "Minute": f"{int(g['game_minute']) + 1}'" if g.get("game_minute") is not None else "?",
             "Film time": g.get("timestamp") or "?"}
            for p in (us, them) for g in p["goals_for"]]
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.caption("No goals logged yet.")
    st.page_link("src/ui/pages/moments.py", label="See every moment on film", icon=":material/arrow_forward:")
