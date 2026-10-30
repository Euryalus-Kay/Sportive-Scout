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

    theme.page_title(role + (" · demo data" if sample else ""), p["team"], color)
    theme.chips([(note, "") for note in context_notes(p)])
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
    cols = st.columns(6)
    cols[0].metric("Possession", f"{poss:.0f}%" if poss is not None else "–", border=True,
                   help="Share of frames with the ball.")
    cols[1].metric("Shots", len(p["shots_for"]), border=True, help=f"{p['rates']['shots_90']:.1f} per 90 minutes")
    cols[2].metric("Goals", len(p["goals_for"]), border=True)
    cols[3].metric("Conceded", len(p["goals_against"]), border=True, help="Goals conceded")
    cols[4].metric("Minutes", f"{p['minutes_covered']:.0f}", border=True,
                   help="Minutes of film analyzed (one frame every 4 seconds).")
    cols[5].metric("Confidence", f"{p['avg_confidence']:.2f}", border=True,
                   help="How clearly the film could be read, from 0 to 1. Below 0.5, treat it as rough.")


def card(label, title):
    box = theme.card()
    with box:
        theme.heading(label, title)
    return box


# ---------- views ----------

def overview(cfg, p, color, which):
    with card("Momentum", "Possession by 5 minutes"):
        st.plotly_chart(charts.momentum(p, color), config=charts.CONFIG, width="stretch", key=f"mom_{which}")
        st.caption("Above the line: more of the ball. Dots are shots (top taken, bottom conceded), stars are goals.")
    left, right = st.columns(2, gap="medium")
    with left:
        findings("Strengths", strengths(p), theme.GOOD, cfg, which)
    with right:
        findings("Weaknesses", weaknesses(p), theme.BAD, cfg, which)


def findings(title, items, color, cfg, which):
    picked = None
    with card(title, f"{len(items)} found" if items else "Nothing clear enough yet"):
        for i, f in enumerate(items):
            moments = [m for m in f.get("moments", []) if m.get("game_id")]
            row, button = st.columns([7, 1], vertical_alignment="center", gap="small")
            with row:
                theme.insight_row(f, color)
            if moments:
                with button.popover(":material/play_arrow:", help="See it on film"):
                    pick = st.pills(f"{len(moments)} moments", [m["timestamp"] for m in moments],
                                    key=f"pill_{which}_{title}_{i}")
                if pick:
                    picked = (next(m for m in moments if m["timestamp"] == pick), f, i)
    if picked:
        m, f, i = picked
        moment_viewer(cfg, m["game_id"], m["seconds"], m["timestamp"], f["title"], f"{which}_{title}_{i}")


def attacking(cfg, p, color, which):
    left, right = st.columns(2, gap="medium")
    with left, card("With the ball", "Where they have the ball"):
        st.plotly_chart(charts.heat_map(p["heat_in"], color=color), config=charts.CONFIG, width="stretch",
                        key=f"heat_in_{which}")
    with right, card("Shots", "Click a shot to see it"):
        event = st.plotly_chart(charts.shot_map(p["shots_for"]), config=charts.CONFIG, width="stretch",
                                on_select="rerun", selection_mode="points", key=f"shots_{which}")
    picked = selected_point(event)
    if picked:
        moment_viewer(cfg, picked[5], picked[6], picked[0], f"{picked[3].capitalize()} by {picked[2]}, {picked[1]}",
                      f"shot_{which}")
    left, right = st.columns(2, gap="medium")
    with left, card("Final third", "Possession by side"):
        sides = {side.capitalize(): share(p["attack_side"], side) for side in ("left", "center", "right")}
        st.plotly_chart(charts.bars(sides, color, percent=True), config=charts.CONFIG, width="stretch",
                        key=f"sides_{which}")
    with right, card("Goals", "By position"):
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
    with left, card("Shots conceded", "Click a shot to see it"):
        event = st.plotly_chart(charts.shot_map(p["shots_against"], against=True), config=charts.CONFIG,
                                width="stretch", on_select="rerun", selection_mode="points", key=f"against_{which}")
    with right, card("Goals conceded", "Minute, scorer and build-up"):
        goals_table(p["goals_against"])
    picked = selected_point(event)
    if picked:
        moment_viewer(cfg, picked[5], picked[6], picked[0], f"Shot conceded ({picked[3]}), {picked[1]}",
                      f"against_{which}")


def shape(cfg, p, color, which):
    left, right = st.columns(2, gap="medium")
    with left, card("Shape", "Without the ball"):
        st.plotly_chart(charts.formation(p["formation_out"], p["block_out_main"], color=color),
                        config=charts.CONFIG, width="stretch", key=f"form_out_{which}")
    with right, card("Shape", "With the ball"):
        st.plotly_chart(charts.formation(p["formation_in"], color=color), config=charts.CONFIG, width="stretch",
                        key=f"form_in_{which}")
    left, right = st.columns(2, gap="medium")
    with left, card("Shapes seen", "Without the ball, share of frames"):
        st.plotly_chart(charts.shapes_seen(p["shape_out"], color), config=charts.CONFIG, width="stretch",
                        key=f"shapes_out_{which}")
    with right, card("Block", "Share of defending frames"):
        blocks = {name.capitalize(): share(p["block_out"], name) for name in ("high", "mid", "low")}
        st.plotly_chart(charts.bars(blocks, color, percent=True), config=charts.CONFIG, width="stretch",
                        key=f"blocks_{which}")


def players(cfg, p, color, which):
    with card("Jersey numbers", "Seen most often near the ball"):
        top = dict(p["players"].most_common(10))
        st.plotly_chart(charts.bars({f"#{k}": v for k, v in top.items()}, color), config=charts.CONFIG,
                        width="stretch", key=f"players_{which}")
        st.caption("Only numbers read clearly on film are counted.")


def goals_table(goals):
    if not goals:
        st.caption("None logged.")
        return
    st.dataframe([{"Minute": f"{int(g['game_minute']) + 1}'" if g.get("game_minute") is not None else "time unknown",
                   "Position": g.get("position") or "unknown",
                   "How": (g.get("build_up") or "unknown").replace("_", " "),
                   "Film time": g.get("timestamp") or "not caught on film"} for g in goals],
                 hide_index=True, width="stretch")
