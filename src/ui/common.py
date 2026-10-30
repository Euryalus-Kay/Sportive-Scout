"""What every page needs: the data (cached), the data source, and the moment viewer."""
import json

import streamlit as st

from src import config, media, sample_data
from src.aggregate import team_profile
from src.ui import theme


# ---------- which data ----------

def has_real_logs():
    """True when at least one of your games has logged moments."""
    if not config.LOGS_DIR.exists():
        return False
    return any(p.stat().st_size > 2 for p in config.LOGS_DIR.glob("*.json")
               if not p.name.endswith("_progress.json"))


def use_sample():
    """True when the app is showing the fake demo games."""
    if "use_sample" not in st.session_state:
        st.session_state.use_sample = not has_real_logs()
    return st.session_state.use_sample


def source_paths(sample):
    if sample:
        return config.SAMPLE_GAMES_FILE, config.SAMPLE_LOGS_DIR, config.SAMPLE_REPORTS_DIR
    return config.GAMES_FILE, config.LOGS_DIR, config.REPORTS_DIR


def fingerprint(logs_dir, games_file):
    """Changes whenever a log file or games.yaml changes, so cached stats refresh."""
    logs = sorted((p.name, p.stat().st_mtime) for p in logs_dir.glob("*.json")) if logs_dir.exists() else []
    return json.dumps([logs, games_file.stat().st_mtime if games_file.exists() else 0])


@st.cache_data(show_spinner="Crunching the numbers...", max_entries=8)
def _profiles(sample, stamp):
    # Both arguments are part of the cache key: a new stamp means fresh numbers.
    games_file, logs_dir, _ = source_paths(sample)
    cfg = config.load_config(games_file)
    m = cfg["matchup"]
    return cfg, team_profile(cfg, m["our_team"], logs_dir), team_profile(cfg, m["opponent"], logs_dir)


def load():
    """(cfg, us, them, sample) for the chosen data, or None when games.yaml isn't ready."""
    sample = use_sample()
    if sample:
        sample_data.ensure()
    games_file, logs_dir, _ = source_paths(sample)
    if not games_file.exists():
        return None
    try:
        cfg = config.load_config(games_file)
    except ValueError as err:
        st.error(f"games.yaml has a problem: {err}")
        return None
    m = cfg["matchup"]
    if not m.get("our_team") or not m.get("opponent") or m["our_team"] == m["opponent"]:
        return None
    return _profiles(sample, fingerprint(logs_dir, games_file)) + (sample,)


def needs_setup():
    """What pages show before there is a matchup to look at."""
    theme.empty("No matchup yet. Add your team and your opponent on the Analyze film page, "
                "or switch the sidebar to the demo data.")
    st.page_link("src/ui/pages/analyze.py", label="Go to Analyze film", icon=":material/movie:")


def no_logs(sample):
    if not sample:
        theme.empty("Nothing has been analyzed for this matchup yet. Run an analysis on the "
                    "Analyze film page and the numbers appear here.")
        st.page_link("src/ui/pages/analyze.py", label="Go to Analyze film", icon=":material/movie:")


def hero(cfg, us, them, sample):
    """The matchup banner with the most important context."""
    chips = [("Demo data (made up teams)", "warn") if sample else ("Your games", "good")]
    for p in (us, them):
        if p["frames_logged"]:
            chips.append((f"{p['team']}: {p['minutes_covered']:.0f} min analyzed, "
                          f"confidence {p['avg_confidence']:.2f}", ""))
        else:
            chips.append((f"{p['team']}: not analyzed yet", "warn"))
    theme.hero(us["team"], them["team"], chips, _games_text(cfg, us["team"]), _games_text(cfg, them["team"]))


def _games_text(cfg, team):
    games = [g for g in cfg["games"] if g.get("analyzed_team_name") == team]
    if not games:
        return "no game film added"
    parts = [f"vs {g.get('other_team_name') or '?'}" + (f" ({g['final_score']})" if g.get("final_score") else "")
             for g in games]
    return f"{len(games)} game{'s' if len(games) > 1 else ''}: " + ", ".join(parts)


# ---------- the film behind a stat ----------

def moment_viewer(cfg, game_id, seconds, timestamp, title, key):
    """Show the frame of a moment and offer a short clip of it."""
    game = next((g for g in cfg["games"] if g["id"] == game_id), None)
    with theme.card():
        theme.label("On film")
        st.markdown(f"**{title}**")
        frame = media.find_frame(game_id, seconds)
        if frame is not None:
            st.image(frame, caption=f"Frame at {timestamp} in the video", width="stretch")
        else:
            st.caption("No extracted frame for this moment" +
                       (" (the demo data has no film)." if game and not media.film_path(game) else "."))
        if game and media.film_path(game):
            if st.button("Play a 12-second clip", key=f"clip_{key}", icon=":material/play_circle:"):
                with st.spinner("Cutting the clip..."):
                    clip = media.cut_clip(game, seconds)
                st.video(str(clip))


def selected_point(event):
    """customdata of the point clicked on a Plotly chart, or None."""
    try:
        points = event.selection.points
    except AttributeError:
        return None
    return points[0].get("customdata") if points else None
