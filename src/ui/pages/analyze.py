"""Analyze film: set up the matchup and games, add videos, run the analysis."""
import os
import re
import subprocess

import pandas as pd
import streamlit as st

from src import config, jobs, media, run
from src.analyzer import load_progress
from src.api_analyzer import (DEFAULT_EFFORT, DEFAULT_MODEL, EFFORTS, MODELS, api_key_available,
                              estimate_cost)
from src.batch_runner import DEFAULT_WORKERS, pending_grids
from src.ui import theme

VIDEO_TYPES = ["mp4", "mov", "m4v", "mkv", "webm", "avi"]
POSITIONS = ["", "GK", "CB", "LB", "RB", "LWB", "RWB", "DM", "CM", "AM", "LM", "RM", "LW", "RW", "ST", "CF"]
HOW = ["", "wide", "central", "counter", "set_piece", "long_ball", "press"]

theme.page_title("Workflow", "Analyze film")
st.caption("Add one game of your team and one of your opponent, then run the analysis. "
           "This page always uses your own games, not the demo data.")

if config.IN_BROWSER:
    with theme.card():
        theme.heading("Browser demo", "Film is analyzed by the app on your computer")
        st.markdown("The demo runs entirely in your browser, so it can't cut video or call Claude. On your "
                    "computer the app does both: add the two games here, press **Analyze**, and the "
                    "numbers fill in as the film is read. A full game takes a few minutes.\n\n"
                    "Setup takes about five minutes with Python and ffmpeg: "
                    "[instructions on GitHub](https://github.com/Euryalus-Kay/Sportive-Scout#setup-once).")
    st.stop()

raw = config.load_raw()
raw.setdefault("matchup", {})
raw.setdefault("games", [])
matchup = raw["matchup"]


def save(data):
    config.save_raw(data)
    st.session_state.use_sample = False
    st.rerun()


# ---------- 1. matchup ----------

with theme.card():
    theme.step(1, "The matchup")
    with st.form("matchup", border=False):
        c = st.columns([2, 2, 1], vertical_alignment="bottom")
        ours = c[0].text_input("Your team", matchup.get("our_team") or "", placeholder="e.g. Lab Schools")
        theirs = c[1].text_input("The opponent you're preparing for", matchup.get("opponent") or "",
                                 placeholder="e.g. Parker")
        if c[2].form_submit_button("Save", width="stretch", type="primary"):
            if not ours.strip() or not theirs.strip() or ours.strip() == theirs.strip():
                st.error("Enter two different team names.")
            else:
                old = (matchup.get("our_team"), matchup.get("opponent"))
                raw["matchup"] = {"our_team": ours.strip(), "opponent": theirs.strip()}
                for g in raw["games"]:          # keep games pointing at the renamed teams
                    if g.get("analyzed_team_name") == old[0]:
                        g["analyzed_team_name"] = ours.strip()
                    elif g.get("analyzed_team_name") == old[1]:
                        g["analyzed_team_name"] = theirs.strip()
                save(raw)

ready = bool(matchup.get("our_team") and matchup.get("opponent"))


# ---------- 2. games ----------

def films():
    config.FILM_DIR.mkdir(exist_ok=True)
    return sorted(p.name for p in config.FILM_DIR.iterdir() if p.suffix.lower().lstrip(".") in VIDEO_TYPES)


def game_status(game):
    """Short status lines for a game card."""
    video = config.FILM_DIR / (game.get("file") or "")
    progress = load_progress(game["id"]) if game.get("id") else {}
    spent = sum(u.get("cost", 0) for state in progress.values() if isinstance(state, dict)
                for u in state.get("usage", {}).values())
    lines = [("Video found" if video.is_file() else f"Video missing: film/{game.get('file')}", video.is_file())]
    for n in (1, 2):
        state = progress.get(f"pass{n}")
        if state:
            done, total = len(state["done_batches"]), state["total_batches"]
            lines.append((f"Pass {n}: {done}/{total} batches logged", done == total))
        elif run.manifest_of(game["id"], n):
            lines.append((f"Pass {n}: frames ready, not analyzed", False))
    return lines, spent


def game_form(game, key):
    """Add or edit one game. Returns the saved entry, or None."""
    names = [matchup["our_team"], matchup["opponent"]]
    videos = films()
    with st.form(f"game_{key}", border=False):
        c = st.columns(2)
        team = c[0].radio("Whose film is this?", names, horizontal=True,
                          index=names.index(game["analyzed_team_name"]) if game.get("analyzed_team_name") in names else 0)
        other = c[1].text_input("Who are they playing in this video?", game.get("other_team_name") or "")
        if not videos:
            st.warning("Upload a video first (below), or copy it into the film/ folder.")
        file = st.selectbox("Video", videos, index=videos.index(game["file"]) if game.get("file") in videos else 0)
        kits = game.get("kit_colors") or {}
        c = st.columns(2)
        kit_a = c[0].text_input("Their kit", kits.get("analyzed_team") or "", placeholder="white shirts, black shorts")
        kit_b = c[1].text_input("Opponent's kit", kits.get("other_team") or "", placeholder="red shirts, red shorts")
        direction = st.radio("In the 1st half, they attack toward the ... of the screen", ["right", "left"],
                             horizontal=True, index=0 if game.get("attacking_direction", "right") == "right" else 1)
        c = st.columns(4)
        kickoff = c[0].text_input("Kickoff (video time)", game.get("kickoff_time") or "00:00")
        half_end = c[1].text_input("1st half ends", game.get("first_half_end") or "", placeholder="optional, mm:ss")
        second = c[2].text_input("2nd half kickoff", game.get("second_half_start") or "", placeholder="mm:ss")
        half_length = c[3].number_input("Minutes per half", 10, 60, int(game.get("half_length") or 45),
                                        help="45 for most adult games, 40 for high school.")
        game_end = st.text_input("Final whistle (video time, optional)", game.get("game_end") or "",
                                 placeholder="h:mm:ss", help="Film after this (celebrations, interviews) is skipped.")
        c = st.columns(3)
        score = c[0].text_input("Final score (their goals first)", game.get("final_score") or "", placeholder="2-1")
        strength = c[1].selectbox("Opponent in this video was", list(config.STRENGTHS),
                                  index=list(config.STRENGTHS).index(game.get("opponent_strength", "similar")))
        playoff = c[2].checkbox("Playoff game", bool(game.get("playoff")))
        st.caption("Goals in this video (so none are missed). Team: analyzed_team = the team whose film this is.")
        goals = st.data_editor(
            pd.DataFrame(game.get("goal_times") or [], columns=["time", "team", "position", "how"]),
            num_rows="dynamic", width="stretch", key=f"goals_{key}", hide_index=True,
            column_config={"time": st.column_config.TextColumn("Video time", help="mm:ss"),
                           "team": st.column_config.SelectboxColumn("Team", options=list(config.TEAMS)),
                           "position": st.column_config.SelectboxColumn("Scorer position", options=POSITIONS),
                           "how": st.column_config.SelectboxColumn("How", options=HOW)})
        c = st.columns(2)
        cameras = {"": "Not sure", "follow": "Follows the ball (Veo, Trace, Pixellot)", "broadcast": "TV or broadcast",
                   "fixed": "Fixed wide camera"}
        camera = c[0].selectbox("Camera", list(cameras), format_func=cameras.get,
                                index=list(cameras).index(game.get("camera") or ""))
        detail = c[1].selectbox("Detail", ["standard", "high"], index=1 if game.get("detail") == "high" else 0,
                                format_func={"standard": "Standard (2x2 grids, cheaper)",
                                             "high": "High (each frame full size, about 2x the cost)"}.get)
        notes = st.text_input("Notes", game.get("notes") or "")
        submitted = st.form_submit_button("Save game", type="primary")
    if not submitted:
        return None
    entry = {
        "id": game.get("id") or _new_id(team, other),
        "file": file, "team_analyzed": "us" if team == matchup["our_team"] else "opponent",
        "analyzed_team_name": team, "other_team_name": other.strip(),
        "kit_colors": {"analyzed_team": kit_a.strip(), "other_team": kit_b.strip()},
        "attacking_direction": direction, "kickoff_time": kickoff.strip(), "first_half_end": half_end.strip(),
        "second_half_start": second.strip(), "half_length": int(half_length), "game_end": game_end.strip() or None,
        "final_score": score.strip(),
        "goal_times": [{k: v for k, v in row.items() if isinstance(v, str) and v.strip()}
                       for row in goals.to_dict("records") if isinstance(row.get("time"), str) and row["time"].strip()],
        "playoff": playoff, "opponent_strength": strength, "camera": camera or None, "detail": detail,
        "notes": notes.strip(),
    }
    try:
        problems = config.validate_config({"matchup": matchup, "games": [config._prepare_game(entry)]})
    except ValueError as err:
        problems = [str(err)]
    if problems:
        st.error("Please fix: " + " ".join(problems))
        return None
    return entry


def _new_id(team, other):
    base = re.sub(r"[^a-z0-9]+", "_", f"{team}_vs_{other or 'game'}".lower()).strip("_")
    ids = {g.get("id") for g in raw["games"]}
    name, n = base, 2
    while name in ids:
        name, n = f"{base}_{n}", n + 1
    return name


with theme.card():
    theme.step(2, "The games")
    if not ready:
        st.info("Save the matchup first.")
    for i, game in enumerate(raw["games"]):
        lines, spent = game_status(game)
        with theme.card():
            c = st.columns([3, 3, 1], vertical_alignment="center")
            with c[0]:
                theme.heading(f"{game.get('id')} · film/{game.get('file')}",
                              f"{game.get('analyzed_team_name')} vs {game.get('other_team_name') or '?'}")
            with c[1]:
                theme.status([(text, theme.GOOD if ok else "#c3c8cf") for text, ok in lines])
            with c[2]:
                theme.heading("Spent", f"${spent:.2f}")
            if ready:
                with st.expander("Edit this game"):
                    entry = game_form(game, f"edit_{i}")
                    if entry:
                        raw["games"][i] = entry
                        save(raw)
                    if st.button("Remove this game", key=f"remove_{i}", icon=":material/delete:"):
                        raw["games"].pop(i)
                        save(raw)
    if ready:
        with st.expander("Add a game", expanded=not raw["games"], icon=":material/add:"):
            entry = game_form({}, "new")
            if entry:
                raw["games"].append(entry)
                save(raw)
        with st.expander("Upload a video", icon=":material/upload:"):
            st.caption("Big files upload faster if you copy them into the project's film/ folder yourself.")
            upload = st.file_uploader("Game video", type=VIDEO_TYPES, label_visibility="collapsed")
            if upload is not None:
                name = re.sub(r"[^A-Za-z0-9._-]+", "_", upload.name)
                target = config.FILM_DIR / name
                if not target.exists():
                    config.FILM_DIR.mkdir(exist_ok=True)
                    with open(target, "wb") as f:
                        f.write(upload.getbuffer())
                st.success(f"Saved as film/{name}. Pick it in the game form.")
        with st.expander("Look at a video (find kickoff, halftime, kits and directions)",
                         icon=":material/frame_inspect:"):
            videos = films()
            if videos:
                c = st.columns([3, 1, 1], vertical_alignment="bottom")
                video = c[0].selectbox("Video", videos, key="peek_video")
                at = c[1].text_input("Time", "00:00", key="peek_time")
                try:
                    info = media.video_info(config.FILM_DIR / video)
                    c[2].caption(f"Length {config.format_time(info['duration'])}, "
                                 f"{info['width']}x{info['height']}, {info['fps']:.2f} fps")
                    seconds = config.parse_time(at) or 0
                    st.image(media.preview_frame(config.FILM_DIR / video, min(seconds, info["duration"] - 0.5)),
                             caption=f"{video} at {config.format_time(seconds)}")
                except (ValueError, OSError, subprocess.CalledProcessError) as err:
                    st.caption(f"Can't show that frame: {err}")
            else:
                st.caption("No videos yet.")


# ---------- 3. run ----------

STAGE_ORDER = list(run.STAGES)


@st.fragment(run_every=2)
def live_progress():
    job = jobs.current()
    if job is None:
        return
    for stage in STAGE_ORDER:
        event = job.stages.get(stage)
        if not event:
            continue
        frac = min(1.0, event["done"] / max(1, event["total"]))
        text = f"{run.STAGES[stage]} · {event['game']} · {event['done']}/{event['total']}"
        if event.get("eta") and frac < 1:
            text += f" · about {int(event['eta'] // 60)}m{int(event['eta'] % 60):02d}s left"
        if event.get("failed"):
            text += f" · {event['failed']} failed (will retry next run)"
        st.progress(frac, text=text)
    cost = job.cost + sum(e.get("cost", 0) for e in job.stages.values() if e.get("game") == job.game)
    st.caption(f"Running for {int(job.elapsed // 60)}m{int(job.elapsed % 60):02d}s"
               + (f" · ${cost:.2f} spent" if job.kind == "analyze" else ""))
    if job.running:
        if st.button("Stop after the requests in flight", icon=":material/stop_circle:"):
            job.stop.set()
    else:
        st.rerun()


with theme.card():
    theme.step(3, "Run the analysis")
    job = jobs.current()
    try:
        cfg = config.load_config() if raw["games"] else {"matchup": matchup, "games": []}
    except ValueError as err:
        st.error(f"games.yaml has a problem: {err}")
        cfg = {"matchup": matchup, "games": []}
    runnable = [g for g in cfg["games"] if g.get("file") and (config.FILM_DIR / g["file"]).is_file()]
    if job and job.running:
        st.info(f"{'Analyzing' if job.kind == 'analyze' else 'Extracting frames for'} "
                f"{', '.join(job.game_ids)}. You can use the other pages meanwhile.")
        live_progress()
    else:
        if job:
            message = {"done": st.success, "stopped": st.warning, "failed": st.error}[job.state]
            message(f"Last run {job.state}" + (f": {job.error}" if job.error else "")
                    + (f" · ${job.cost:.2f} spent" if job.kind == "analyze" else "")
                    + f" · {int(job.elapsed // 60)}m{int(job.elapsed % 60):02d}s")
            for note in job.notes[:8]:
                st.caption(note)
        problems = config.validate_config(cfg) if cfg["games"] else []
        if problems:
            st.error("Fix these first: " + " ".join(problems))
        elif not runnable:
            st.caption("Add a game with its video above to start.")
        else:
            picked = st.multiselect("Games", [g["id"] for g in runnable], default=[g["id"] for g in runnable])
            if api_key_available():
                c = st.columns([3, 2, 2, 2])
                model = c[0].selectbox("Model", list(MODELS), index=list(MODELS).index(DEFAULT_MODEL),
                                       format_func=lambda m: MODELS[m]["label"])
                effort = c[1].selectbox("Effort", EFFORTS, index=EFFORTS.index(DEFAULT_EFFORT),
                                        help="Higher effort reads hard frames more carefully but is slower.")
                workers = c[2].slider("Requests at once", 1, 16, DEFAULT_WORKERS,
                                      help="More is faster. Lower it if your API key hits rate limits.")
                quick = c[3].toggle("Quick test (5 min)", help="Only the first 5 minutes of each game.")
                minutes = 5 if quick else None
                plan = [(g, pending_grids(g["id"], 1) if run.pass1_ready(g, minutes) else run.planned_grids(g, minutes))
                        for g in runnable if g["id"] in picked]
                frames = sum(n * run.extract.layout(g)[1] for g, n in plan)
                cost = sum(estimate_cost(n, model, frames_per_image=run.extract.layout(g)[1]) for g, n in plan)
                st.caption(f"{frames} frames to analyze in Pass 1 · rough cost "
                           f"${cost:.2f} (key moments add 10-20%). Already analyzed "
                           "parts are skipped, and stopping keeps everything finished so far.")
                if st.button(f"Analyze {len(picked)} game{'s' if len(picked) != 1 else ''}", type="primary",
                             disabled=not picked, icon=":material/play_arrow:"):
                    jobs.start("analyze", picked, run.Options(minutes=minutes, workers=workers,
                                                              model=model, effort=effort))
                    st.rerun()
            else:
                st.warning("No Claude API key found, so the automatic analysis is off. You can still "
                           "extract frames here and let Claude Code log them (see below).")
                with st.form("api_key", border=False):
                    key = st.text_input("Paste an Anthropic API key to turn it on", type="password",
                                        help="Saved in the project's .env file on this computer (git-ignored).")
                    if st.form_submit_button("Save key") and key.strip().startswith("sk-"):
                        with open(config.ENV_FILE, "a") as f:
                            f.write(f"\nANTHROPIC_API_KEY={key.strip()}\n")
                        os.environ["ANTHROPIC_API_KEY"] = key.strip()
                        st.rerun()
                if st.button("Extract frames only", disabled=not picked, icon=":material/movie:"):
                    jobs.start("extract", picked, run.Options())
                    st.rerun()

with st.expander("No API key? Let Claude Code do the logging", icon=":material/terminal:"):
    st.markdown(
        "1. Extract the frames (button above, or `python -m src.extract --game GAME_ID`).\n"
        "2. In Claude Code, ask: *\"log the next batch for GAME_ID\"*. It runs "
        "`python -m src.analyzer claim --game GAME_ID`, looks at the grids and saves them.\n"
        "3. To go faster, ask Claude Code to use several agents at once: each one claims a different "
        "batch, so they never collide.\n"
        "4. Then `python -m src.extract --game GAME_ID --pass 2` for the key moments, and log those too.")
