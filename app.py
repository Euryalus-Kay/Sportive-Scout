"""Sportive Scout: the local interface.

Run with:  streamlit run app.py
"""
import json

import matplotlib.pyplot as plt
import streamlit as st

from src import config, sample_data, visualize as viz
from src.aggregate import team_profile
from src.analyzer import load_progress
from src.insights import context_notes, game_plan, strengths, weaknesses
from src.report import build, game_plan_markdown

st.set_page_config(page_title="Sportive Scout", page_icon="⚽", layout="wide")


# ---------- data ----------

def source_paths(sample):
    if sample:
        return config.SAMPLE_GAMES_FILE, config.SAMPLE_LOGS_DIR, config.SAMPLE_REPORTS_DIR
    return config.GAMES_FILE, config.LOGS_DIR, config.REPORTS_DIR


def logs_fingerprint(logs_dir):
    """Changes whenever a log file changes, so cached stats refresh."""
    if not logs_dir.exists():
        return ""
    return json.dumps(sorted((p.name, p.stat().st_mtime) for p in logs_dir.glob("*.json")))


@st.cache_data(show_spinner="Crunching the numbers...")
def load_profiles(sample, _fingerprint, _yaml_mtime):
    games_file, logs_dir, _ = source_paths(sample)
    cfg = config.load_config(games_file)
    m = cfg["matchup"]
    return cfg, team_profile(cfg, m["our_team"], logs_dir), team_profile(cfg, m["opponent"], logs_dir)


def show(fig):
    st.pyplot(fig, width="stretch")
    plt.close(fig)


# ---------- team tab ----------

def team_tab(p, label):
    st.subheader(f"{p['team']} ({label})")
    if not p["frames_logged"]:
        st.info("No moments logged for this team yet. See the **Analysis progress** tab.")

    poss = p["possession_pct"]
    c = st.columns(6)
    c[0].metric("Possession", f"{poss:.0f}%" if poss is not None else "–")
    c[1].metric("Shots", len(p["shots_for"]))
    c[2].metric("Goals", len(p["goals_for"]))
    c[3].metric("Goals conceded", len(p["goals_against"]))
    c[4].metric("Minutes analyzed", f"{p['minutes_covered']:.0f}")
    c[5].metric("Avg confidence", f"{p['avg_confidence']:.2f}")
    for note in context_notes(p):
        st.caption(note)

    key = p["team"]
    left, right = st.columns(2)
    with left:
        mode = st.radio("Formation", ["Without the ball", "With the ball"], horizontal=True, key=f"form_{key}")
        if mode == "With the ball":
            show(viz.formation_map(p["formation_in"], None, "Shape with the ball"))
        else:
            show(viz.formation_map(p["formation_out"], p["block_out_main"], "Shape without the ball"))
    with right:
        mode = st.radio("Ball heat map", ["All frames", "When they have the ball", "When opponents have it"],
                        horizontal=True, key=f"heat_{key}")
        if mode == "All frames":
            show(viz.heat_map(p["heat_all"], "Where the ball is"))
        elif mode == "When they have the ball":
            show(viz.heat_map(p["heat_in"], "Ball location in possession"))
        else:
            show(viz.heat_map(p["heat_out"], "Ball location out of possession", cmap=viz.ORANGES))

    left, right = st.columns(2)
    with left:
        mode = st.radio("Shots", ["Shots taken", "Shots conceded"], horizontal=True, key=f"shots_{key}")
        if mode == "Shots taken":
            show(viz.shot_map(p["shots_for"], "Shots taken"))
        else:
            show(viz.shot_map(p["shots_against"], "Shots conceded", against=True))
    with right:
        show(viz.bar_chart(p["goals_by_position"], "Goals by position", "goals"))
        goals_table(p["goals_for"], "Goals scored")
        goals_table(p["goals_against"], "Goals conceded")

    left, right = st.columns(2)
    with left:
        show(viz.count_map(p["turnovers"], "Where they lose the ball"))
    with right:
        show(viz.possession_chart(p))
        show(viz.side_chart(p["attack_side"], "Final-third attacks by side"))

    left, right = st.columns(2)
    with left:
        findings_list("Strengths", strengths(p), "How to stop it")
    with right:
        findings_list("Weaknesses", weaknesses(p), "How to use it")


def goals_table(goals, title):
    st.markdown(f"**{title}**")
    if not goals:
        st.caption("None logged.")
        return
    rows = [{"Time": g.get("timestamp"), "Minute": _minute(g.get("game_minute")),
             "Position": g.get("position") or "unknown", "How": g.get("build_up") or "unknown"}
            for g in goals]
    st.dataframe(rows, hide_index=True, width="stretch")


def _minute(m):
    return f"{int(m) + 1}'" if m is not None else "?"


def findings_list(title, items, action_label):
    st.markdown(f"### {title}")
    if not items:
        st.caption("Nothing clear enough to call yet.")
    for f in items:
        with st.expander(f"{f['title']}  ·  {f['evidence']}"):
            st.write(f["detail"])
            st.markdown(f"**{action_label}:** {f['action']}")
            if f["timestamps"]:
                st.caption("Check on film at: " + ", ".join(f["timestamps"]))


# ---------- game plan tab ----------

def plan_tab(us, them, sample):
    plan = game_plan(us, them)
    st.subheader(f"Game plan: {us['team']} vs {them['team']}")
    for note in plan["context"]:
        st.caption(note)

    left, right = st.columns(2)
    with left:
        st.markdown("### Exploit their weaknesses")
        for m in plan["exploit"]:
            plan_card(m, "Fits our strength", "success")
        if not plan["exploit"]:
            st.caption("No clear weaknesses yet.")
    with right:
        st.markdown("### Counter their strengths")
        for m in plan["counter"]:
            plan_card(m, "Danger: hits our weakness", "warning")
        if not plan["counter"]:
            st.caption("No clear strengths yet.")

    if plan["fix"]:
        st.markdown("### Our weaknesses they could target")
        for w in plan["fix"]:
            st.error(f"**{w['title']}**: work on this in training this week.")

    left, right = st.columns(2)
    with left:
        st.markdown("### Set pieces")
        for n in plan["set_pieces"]:
            st.write("- " + n)
    with right:
        st.markdown("### First 10-15 minutes checklist")
        for i, c in enumerate(plan["first_15"]):
            st.checkbox(c, key=f"check_{i}")

    st.divider()
    _, _, reports_dir = source_paths(sample)
    images = reports_dir / "images"
    st.download_button("Download game plan (.md)",
                       game_plan_markdown(us, them, plan, images, reports_dir),
                       file_name="game_plan.md")
    if st.button("Save all reports and PNGs to the reports folder"):
        games_file, logs_dir, reports_dir = source_paths(sample)
        reports_dir.mkdir(parents=True, exist_ok=True)
        build(config.load_config(games_file), logs_dir, reports_dir)
        st.success(f"Saved to {reports_dir.relative_to(config.ROOT)}/")


def plan_card(match, match_label, tone):
    item = match["item"]
    with st.container(border=True):
        st.markdown(f"**{item['title']}**  \n`{item['evidence']}`")
        st.write(item["action"])
        if match["matches"]:
            getattr(st, tone)(f"{match_label}: " + "; ".join(match["matches"]))


# ---------- progress tab ----------

def progress_tab(cfg, sample):
    st.subheader("Analysis progress")
    if sample:
        st.info("Sample mode uses generated fake logs, so there is nothing to analyze.")
        return
    for game in cfg["games"]:
        with st.container(border=True):
            st.markdown(f"**{game['id']}**: {game.get('analyzed_team_name')} vs "
                        f"{game.get('other_team_name')}  (`film/{game.get('file')}`)")
            video_ok = (config.FILM_DIR / game.get("file", "")).exists()
            st.write(("✅" if video_ok else "❌") + " video in film/")
            progress = load_progress(game["id"])
            for pass_no in (1, 2):
                frames_ok = (config.FRAMES_DIR / game["id"] / f"pass{pass_no}" / "manifest.json").exists()
                state = progress.get(f"pass{pass_no}")
                if state:
                    done, total = len(state["done_batches"]), state["total_batches"]
                    st.progress(done / total if total else 0, text=f"Pass {pass_no}: {done}/{total} batches logged")
                else:
                    st.write(f"Pass {pass_no}: " + ("frames ready, not logged yet" if frames_ok else "frames not extracted"))
    st.markdown("**Next steps** (run in the VS Code terminal):")
    st.code("python -m src.extract --game GAME_ID --minutes 5   # test extraction\n"
            "python -m src.extract --game GAME_ID               # full game, Pass 1\n"
            "# then ask Claude Code: \"log the next batch for GAME_ID\"\n"
            "python -m src.extract --game GAME_ID --pass 2      # key moments\n"
            "python -m src.report                               # write reports", language="bash")


# ---------- page ----------

def main():
    st.title("⚽ Sportive Scout")
    has_real = config.GAMES_FILE.exists()
    choice = st.sidebar.radio("Data", ["Sample (fake demo)", "My games (games.yaml)"],
                              index=0, disabled=not has_real)
    sample = choice.startswith("Sample")
    if sample:
        sample_data.ensure()
        st.warning("You are looking at **fake demo data**. Switch to *My games* in the sidebar "
                   "once your film has been analyzed.")

    games_file, logs_dir, _ = source_paths(sample)
    cfg = config.load_config(games_file)
    m = cfg["matchup"]
    if not m.get("our_team") or not m.get("opponent"):
        st.error("Fill in `matchup: our_team` and `opponent` in games.yaml first.")
        return
    cfg, us, them = load_profiles(sample, logs_fingerprint(logs_dir), games_file.stat().st_mtime)

    st.sidebar.markdown(f"**Your team:** {us['team']}  \n**Opponent:** {them['team']}")
    st.sidebar.caption("Fields are drawn with the team attacking left → right; "
                       "the top touchline is their left side.")

    tabs = st.tabs([f"🔵 {us['team']} (you)", f"🔴 {them['team']} (opponent)",
                    "📋 Game plan", "⚙️ Analysis progress"])
    with tabs[0]:
        team_tab(us, "your team")
    with tabs[1]:
        team_tab(them, "opponent")
    with tabs[2]:
        plan_tab(us, them, sample)
    with tabs[3]:
        progress_tab(cfg, sample)


main()
