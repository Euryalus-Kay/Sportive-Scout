"""A team's scouting page (used for both teams)."""
import streamlit as st

from src.aggregate import share
from src.insights import context_notes, strengths, weaknesses
from src.ui import charts, theme
from src.ui.common import load, moment_viewer, needs_setup, no_logs, selected_point

VIEWS = ["Overview", "Attacking", "Defending", "Shape", "Players"]


def page(which):
    data = load()
    if data is None:
        needs_setup()
        return
    cfg, us, them, sample = data
    p, color = (us, theme.US) if which == "us" else (them, theme.THEM)
    role = "Your team" if which == "us" else "Opponent"

    top = st.columns([3, 2])
    with top[0]:
        theme.label(role + (" · demo data" if sample else ""))
        st.markdown(f"<div class='ss-team'><span class='ss-dot' style='background:{color}'></span>"
                    f"{theme.esc(p['team'])}</div>", unsafe_allow_html=True)
    with top[1]:
        notes = context_notes(p)
        if notes:
            with st.popover("Things to keep in mind", icon=":material/info:", width="stretch"):
                for note in notes:
                    st.markdown(f"- {note}")
    if not p["frames_logged"]:
        no_logs(sample)
        return

    kpis(p)
    view = st.segmented_control("View", VIEWS, default="Overview", key=f"view_{which}",
                                label_visibility="collapsed") or "Overview"
    {"Overview": overview, "Attacking": attacking, "Defending": defending,
     "Shape": shape, "Players": players}[view](cfg, p, color, which)


def kpis(p):
    poss = p["possession_pct"]
    spark = [round(v) for v in charts.possession_by_bin(p) if v is not None]
    cols = st.columns(6)
    cols[0].metric("Possession", f"{poss:.0f}%" if poss is not None else "–", border=True, height="stretch",
                   chart_data=spark if len(spark) > 2 else None, chart_type="area",
                   help="Share of frames where this team had the ball (5-minute trend in the chart).")
    cols[1].metric("Shots", len(p["shots_for"]), border=True, height="stretch",
                   help=f"{p['rates']['shots_90']:.1f} per 90 minutes")
    cols[2].metric("Goals", len(p["goals_for"]), border=True, height="stretch")
    cols[3].metric("Conceded", len(p["goals_against"]), border=True, height="stretch", help="Goals conceded")
    cols[4].metric("Minutes", f"{p['minutes_covered']:.0f}", border=True, height="stretch",
                   help="Minutes of film analyzed (one frame every 4 seconds).")
    cols[5].metric("Confidence", f"{p['avg_confidence']:.2f}", border=True, height="stretch",
                   help="How clearly the film could be read, from 0 to 1. Below 0.5 means treat it as rough.")


def card(label, title):
    box = theme.card()
    with box:
        theme.label(label)
        st.markdown(f"**{title}**")
    return box


# ---------- views ----------

def overview(cfg, p, color, which):
    with card("Momentum", "Who had the ball, 5 minutes at a time"):
        st.plotly_chart(charts.momentum(p, color), config=charts.CONFIG, width="stretch", key=f"mom_{which}")
        st.caption("Bars above the line: more of the ball than the opponent. Dots: shots (top = taken, "
                   "bottom = conceded), stars: goals.")
    left, right = st.columns(2, gap="medium")
    with left:
        findings("Strengths", strengths(p), theme.GOOD if which == "us" else theme.THEM,
                 "How to stop it" if which == "them" else "Keep doing it", cfg, which)
    with right:
        findings("Weaknesses", weaknesses(p), theme.THEM if which == "us" else theme.GOOD,
                 "How to use it" if which == "them" else "Fix it", cfg, which)


def findings(title, items, tone, action_label, cfg, which):
    with card(title, f"{len(items)} found" if items else "Nothing clear enough yet"):
        for i, f in enumerate(items):
            theme.finding_card(f, tone, action_label)
            moments = [m for m in f.get("moments", []) if m.get("game_id")]
            if moments:
                with st.expander(f"See it on film · {len(moments)} moment{'s' if len(moments) > 1 else ''}",
                                 icon=":material/play_circle:"):
                    pick = st.pills("Moment", [m["timestamp"] for m in moments], key=f"pill_{which}_{title}_{i}",
                                    label_visibility="collapsed")
                    if pick:
                        m = next(m for m in moments if m["timestamp"] == pick)
                        moment_viewer(cfg, m["game_id"], m["seconds"], pick, f["title"], f"{which}_{title}_{i}")


def attacking(cfg, p, color, which):
    left, right = st.columns(2, gap="medium")
    with left, card("With the ball", "Where they have the ball"):
        st.plotly_chart(charts.heat_map(p["heat_in"], color=color), config=charts.CONFIG, width="stretch",
                        key=f"heat_in_{which}")
    with right, card("Shots", "Every shot they took (click one to see it)"):
        event = st.plotly_chart(charts.shot_map(p["shots_for"]), config=charts.CONFIG, width="stretch",
                                on_select="rerun", selection_mode="points", key=f"shots_{which}")
    picked = selected_point(event)
    if picked:
        moment_viewer(cfg, picked[5], picked[6], picked[0], f"{picked[3].capitalize()} by {picked[2]}, {picked[1]}",
                      f"shot_{which}")
    left, right = st.columns(2, gap="medium")
    with left, card("Final third", "Which side their attacks come down"):
        sides = {side.capitalize(): share(p["attack_side"], side) for side in ("left", "center", "right")}
        st.plotly_chart(charts.bars(sides, color, percent=True), config=charts.CONFIG, width="stretch",
                        key=f"sides_{which}")
    with right, card("Goals", "Who scores and how"):
        st.plotly_chart(charts.bars(p["goals_by_position"], color), config=charts.CONFIG, width="stretch",
                        key=f"gpos_{which}")
        goals_table(p["goals_for"])


def defending(cfg, p, color, which):
    left, right = st.columns(2, gap="medium")
    with left, card("Without the ball", "Where the opponent has the ball"):
        st.plotly_chart(charts.heat_map(p["heat_out"], color=theme.THEM if which == "us" else theme.US),
                        config=charts.CONFIG, width="stretch", key=f"heat_out_{which}")
    with right, card("Turnovers", "Where they lose the ball"):
        st.plotly_chart(charts.count_map(p["turnovers"], color=theme.BAD), config=charts.CONFIG, width="stretch",
                        key=f"turn_{which}")
    left, right = st.columns(2, gap="medium")
    with left, card("Shots conceded", "Where opponents shoot from (click one to see it)"):
        event = st.plotly_chart(charts.shot_map(p["shots_against"], against=True), config=charts.CONFIG,
                                width="stretch", on_select="rerun", selection_mode="points", key=f"against_{which}")
    with right, card("Goals conceded", "How they concede"):
        goals_table(p["goals_against"])
    picked = selected_point(event)
    if picked:
        moment_viewer(cfg, picked[5], picked[6], picked[0], f"Shot conceded ({picked[3]}), {picked[1]}",
                      f"against_{which}")


def shape(cfg, p, color, which):
    left, right = st.columns(2, gap="medium")
    with left, card("Without the ball", "Defensive shape"):
        st.plotly_chart(charts.formation(p["formation_out"], p["block_out_main"], color=color),
                        config=charts.CONFIG, width="stretch", key=f"form_out_{which}")
    with right, card("With the ball", "Attacking shape"):
        st.plotly_chart(charts.formation(p["formation_in"], color=color), config=charts.CONFIG, width="stretch",
                        key=f"form_in_{which}")
    left, right = st.columns(2, gap="medium")
    with left, card("Shapes seen", "Without the ball"):
        st.plotly_chart(charts.shapes_seen(p["shape_out"], color), config=charts.CONFIG, width="stretch",
                        key=f"shapes_out_{which}")
    with right, card("How high they defend", "Share of defending frames"):
        blocks = {name.capitalize(): share(p["block_out"], name) for name in ("high", "mid", "low")}
        st.plotly_chart(charts.bars(blocks, color, percent=True), config=charts.CONFIG, width="stretch",
                        key=f"blocks_{which}")


def players(cfg, p, color, which):
    with card("Jersey numbers", "Seen most often near the ball"):
        top = dict(p["players"].most_common(10))
        st.plotly_chart(charts.bars({f"#{k}": v for k, v in top.items()}, color), config=charts.CONFIG,
                        width="stretch", key=f"players_{which}")
        st.caption("Only numbers that could be read clearly on film are counted, so this shows who is "
                   "involved, not who is best.")


def goals_table(goals):
    if not goals:
        st.caption("None logged.")
        return
    st.dataframe([{"Minute": f"{int(g['game_minute']) + 1}'" if g.get("game_minute") is not None else "?",
                   "Position": g.get("position") or "unknown",
                   "How": (g.get("build_up") or "unknown").replace("_", " "),
                   "Film time": g.get("timestamp") or "?"} for g in goals],
                 hide_index=True, width="stretch")
