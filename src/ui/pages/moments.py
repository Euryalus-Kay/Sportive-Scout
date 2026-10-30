"""Moments: every logged event in one searchable list, each one viewable on film."""
import streamlit as st

from src.ui import theme
from src.ui.common import load, moment_viewer, needs_setup, no_logs

TYPES = {"shot": "Shots", "goal": "Goals", "turnover": "Turnovers", "set_piece": "Set pieces",
         "press": "Presses", "cross": "Crosses", "long_ball": "Long balls", "counter": "Counters"}

data = load()
if data is None:
    needs_setup()
    st.stop()
cfg, us, them, sample = data
theme.page_title("Moments" + (" · demo data" if sample else ""), "Every logged moment")
if not (us["frames_logged"] or them["frames_logged"]):
    no_logs(sample)
    st.stop()


def rows_for(p):
    """One row per event of a team (shots, goals and everything else they did)."""
    rows = []
    for e in p["shots_for"] + p["events_for"]:
        kind = "goal" if e["type"] == "shot" and e.get("outcome") == "goal" else e["type"]
        detail = {
            "shot": f"{(e.get('outcome') or '?').replace('_', ' ')} · {e.get('position') or '?'}",
            "goal": f"{e.get('position') or '?'} · {(e.get('build_up') or '?').replace('_', ' ')}",
            "set_piece": (e.get("subtype") or "").replace("_", " "),
        }.get(kind, "")
        rows.append({"Team": p["team"], "Event": TYPES.get(kind, kind), "Detail": detail,
                     "Minute": int(e["game_minute"]) + 1 if e.get("game_minute") is not None else None,
                     "Film time": e.get("timestamp") or "", "half": e.get("half"),
                     "game_id": e.get("game_id"), "seconds": e.get("video_seconds")})
    return rows


def keep(row, team, kinds, half):
    if team not in (None, "Both") and row["Team"] != team:
        return False
    if kinds and row["Event"] not in kinds:
        return False
    return half in (None, "All") or row["half"] == (1 if half == "1st" else 2)


with theme.card():
    cols = st.columns([2, 3, 2])
    team = cols[0].segmented_control("Team", ["Both", us["team"], them["team"]], default="Both", key="m_team")
    kinds = cols[1].multiselect("Events", list(TYPES.values()), default=["Shots", "Goals"], key="m_kinds")
    half = cols[2].segmented_control("Half", ["All", "1st", "2nd"], default="All", key="m_half")
    rows = [r for r in rows_for(us) + rows_for(them) if keep(r, team, kinds, half)]
    rows.sort(key=lambda r: (r["Team"], r["seconds"] or 0))
    st.caption(f"{len(rows)} moments · click a row to see it")
    event = st.dataframe(rows, hide_index=True, width="stretch", height=420, on_select="rerun",
                         selection_mode="single-row", key="m_table",
                         column_order=["Team", "Minute", "Event", "Detail", "Film time"],
                         column_config={"Minute": st.column_config.NumberColumn(format="%d'")})

picked = event.selection.rows
if picked:
    r = rows[picked[0]]
    moment_viewer(cfg, r["game_id"], r["seconds"], r["Film time"],
                  f"{r['Team']}: {r['Event'].lower().rstrip('s')} {r['Detail']}".strip(), "moments")
