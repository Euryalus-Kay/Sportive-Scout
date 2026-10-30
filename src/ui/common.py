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
    theme.empty("No matchup yet. Add both teams on Analyze film, or switch the sidebar to demo data.")
    st.page_link("src/ui/pages/analyze.py", label="Analyze film", icon=":material/arrow_forward:")


def no_logs(sample):
    if not sample:
        theme.empty("No analyzed film for this matchup yet.")
        st.page_link("src/ui/pages/analyze.py", label="Analyze film", icon=":material/arrow_forward:")


def hero(cfg, us, them, sample):
    """The matchup title with the context that matters."""
    st.html(f'<div class="pm-label">Matchup</div><div class="pm-h1">'
            f'<span class="pm-dot" style="background:{theme.US}"></span>{theme.esc(us["team"])}'
            f'<span style="color:{theme.MUTED};font-weight:500;margin:0 12px">vs</span>'
            f'<span class="pm-dot" style="background:{theme.THEM}"></span>{theme.esc(them["team"])}</div>')
    items = [("Demo data, made-up teams", "warn")] if sample else []
    for p in (us, them):
        if p["frames_logged"]:
            items.append((f"{p['team']} · {_games_text(cfg, p['team'])} · {p['minutes_covered']:.0f} min", ""))
        else:
            items.append((f"{p['team']} · not analyzed yet", "warn"))
    theme.chips(items)


def _games_text(cfg, team):
    games = [g for g in cfg["games"] if g.get("analyzed_team_name") == team]
    if not games:
        return "no film"
    return ", ".join(f"vs {g.get('other_team_name') or '?'}" + (f" {g['final_score']}" if g.get("final_score") else "")
                     for g in games)


# ---------- the film behind a stat ----------

def moment_viewer(cfg, game_id, seconds, timestamp, title, key):
    """Show the frame of a moment and offer a short clip of it."""
    game = next((g for g in cfg["games"] if g["id"] == game_id), None)
    with theme.card():
        theme.heading(f"Film · {timestamp}", title)
        frame = media.find_frame(game_id, seconds)
        if frame is not None:
            st.image(frame, width="stretch")
        else:
            st.caption("No frame saved for this moment" +
                       (" (demo data has no film)." if game and not media.film_path(game) else "."))
        if game and media.film_path(game):
            if st.button("Play clip", key=f"clip_{key}", icon=":material/play_arrow:"):
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
