"""Builds a static game page (website/games/<slug>/) from a finished analysis.

    python website/build_game.py u-high-vs-lemont

It needs the analyzed games (games.yaml, logs/, frames/, film/) on this computer.
The page holds everything the app shows, already worked out: every team's numbers,
insights, interactive charts, every logged moment with its frame, and a clip of
every goal and shot. It is plain HTML and JavaScript, so it opens anywhere, fast.
"""
import csv
import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config, media  # noqa: E402
from src.aggregate import share, team_profile  # noqa: E402
from src.insights import context_notes, game_plan, set_piece_numbers, setup, strengths, weaknesses  # noqa: E402
from src.ui import charts, theme  # noqa: E402

PAGE_DIR = ROOT / "website" / "games"
TEMPLATE = ROOT / "website" / "game_template"
ROUTINE = {"throw_in", "goal_kick", "kickoff"}   # set pieces that don't get a clip
TYPES = {"shot": "Shot", "turnover": "Turnover", "press": "Press", "cross": "Cross",
         "long_ball": "Long ball", "counter": "Counter", "set_piece": "Set piece"}


def chart(fig):
    return json.loads(fig.to_json())


def moment_id(game_id, seconds, kind):
    return f"{game_id}_{int(round(seconds))}_{kind}"


def detail(e):
    if e["type"] == "shot":
        bits = [(e.get("outcome") or "shot").replace("_", " ")]
        if e.get("position") and e["position"] != "unknown":
            bits.append(e["position"])
        if e.get("build_up") and e["build_up"] != "unknown":
            bits.append(e["build_up"].replace("_", " "))
        return " · ".join(bits)
    if e["type"] == "set_piece":
        return (e.get("subtype") or "set piece").replace("_", " ")
    return ""


class Media:
    """Copies frames and cuts clips into the page folder, once per moment."""

    def __init__(self, out_dir, games):
        self.out = out_dir / "media"
        (self.out / "frames").mkdir(parents=True, exist_ok=True)
        (self.out / "clips").mkdir(parents=True, exist_ok=True)
        self.games = {g["id"]: g for g in games}

    def frame(self, game_id, seconds):
        name = f"{game_id}_{int(round(seconds))}.jpg"
        path = self.out / "frames" / name
        if not path.exists():
            found = media.find_frame(game_id, seconds)
            if found is None:
                return None
            from PIL import Image
            image = found if isinstance(found, Image.Image) else Image.open(found)
            image.convert("RGB").resize((960, int(image.height * 960 / image.width))).save(path, quality=80)
        return f"media/frames/{name}"

    def clip(self, game_id, seconds):
        name = f"{game_id}_{int(round(seconds))}.mp4"
        path = self.out / "clips" / name
        if not path.exists():
            made = media.cut_clip(self.games[game_id], seconds)
            if not made:
                return None
            shutil.copy(made, path)
        return f"media/clips/{name}"


def team_block(cfg, name, color, role, store, moments_by_key):
    p = team_profile(cfg, name)
    rates = p["rates"]

    def with_moments(findings):
        out = []
        for f in findings:
            ids = [moments_by_key.get((m["game_id"], int(round(m["seconds"]))))
                   for m in f.get("moments", []) if m.get("game_id") and m.get("seconds") is not None]
            out.append({"stat": f["stat"], "label": f["label"], "basis": f["basis"], "moments": [i for i in ids if i]})
        return out

    goals = []
    for g in sorted(p["goals_for"], key=lambda g: (g.get("video_seconds") is None, g.get("video_seconds") or 0)):
        sec = g.get("video_seconds")
        goals.append({
            "minute": f"{int(g['game_minute']) + 1}'" if g.get("game_minute") is not None else "time unknown",
            "film": g.get("timestamp") or "not caught on film",
            "game": g.get("game_id"),
            "moment": moments_by_key.get((g.get("game_id"), int(round(sec)))) if sec is not None else None,
        })
    sides = {s.capitalize(): share(p["attack_side"], s) for s in ("left", "center", "right")}
    blocks = {b.capitalize(): share(p["block_out"], b) for b in ("high", "mid", "low")}
    top_players = dict(p["players"].most_common(10))
    return {
        "name": name, "color": color, "role": role,
        "games": [{"vs": g["other_team_name"], "score": g.get("final_score"), "id": g["id"]} for g in p["games"]],
        "kpis": {"possession": p["possession_pct"], "shots": len(p["shots_for"]), "goals": len(p["goals_for"]),
                 "conceded": len(p["goals_against"]), "minutes": round(p["minutes_covered"]),
                 "confidence": round(p["avg_confidence"], 2)},
        "rates": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in rates.items()},
        "goals_90": round(len(p["goals_for"]) * p["per90"], 1),
        "conceded_90": round(len(p["goals_against"]) * p["per90"], 1),
        "notes": context_notes(p),
        "strengths": with_moments(strengths(p)),
        "weaknesses": with_moments(weaknesses(p)),
        "setup": setup(p),
        "set_pieces": set_piece_numbers(p),
        "goals": goals,
        "charts": {
            "momentum": chart(charts.momentum(p, color)),
            "heat_in": chart(charts.heat_map(p["heat_in"], color=color)),
            "heat_out": chart(charts.heat_map(p["heat_out"], color=theme.THEM if color == theme.US else theme.US)),
            "shots_for": chart(charts.shot_map(p["shots_for"])),
            "shots_against": chart(charts.shot_map(p["shots_against"], against=True)),
            "turnovers": chart(charts.count_map(p["turnovers"], color=theme.BAD)),
            "sides": chart(charts.bars(sides, color, percent=True)),
            "blocks": chart(charts.bars(blocks, color, percent=True)),
            "goals_by_position": chart(charts.bars(p["goals_by_position"], color)),
            "players": chart(charts.bars({f"#{k}": v for k, v in top_players.items()}, color)),
        },
    }


def collect_moments(cfg, teams, store):
    """Every logged event once (each belongs to the team that did it), with frame and clip."""
    rows, by_key = [], {}
    for name in teams:
        p = team_profile(cfg, name)
        for e in p["shots_for"] + [e for e in p["events_for"] if e["type"] != "shot"]:
            sec = e.get("video_seconds")
            kind = e["type"]
            key = (e.get("game_id"), int(round(sec))) if sec is not None else None
            mid = moment_id(e["game_id"], sec, kind) if sec is not None else f"{e['game_id']}_unknown_{len(rows)}"
            if any(r["id"] == mid for r in rows):
                continue
            row = {
                "id": mid, "game": e.get("game_id"), "team": name, "type": TYPES.get(kind, kind),
                "goal": kind == "shot" and e.get("outcome") == "goal",
                "detail": detail(e),
                "minute": int(e["game_minute"]) + 1 if e.get("game_minute") is not None else None,
                "half": e.get("half"), "film": e.get("timestamp") or "", "seconds": sec,
                "frame": store.frame(e["game_id"], sec) if sec is not None else None,
                "clip": store.clip(e["game_id"], sec) if sec is not None and e.get("subtype") not in ROUTINE else None,
            }
            rows.append(row)
            if key:
                by_key.setdefault(key, mid)
    rows.sort(key=lambda r: (r["game"], r["seconds"] is None, r["seconds"] or 0))
    return rows, by_key


def head_to_head(us, them):
    r, s = us["rates"], them["rates"]
    return [
        ("Goals per 90", us["goals_90"], them["goals_90"], "{:.1f}", True),
        ("Goals conceded per 90", us["conceded_90"], them["conceded_90"], "{:.1f}", False),
        ("Shots per 90", r["shots_90"], s["shots_90"], "{:.1f}", True),
        ("Shots conceded per 90", r["shots_against_90"], s["shots_against_90"], "{:.1f}", False),
        ("Shots on target", r["on_target_pct"], s["on_target_pct"], "{:.0f}%", True),
        ("Possession in the final third", r["final_third_pct"], s["final_third_pct"], "{:.0f}%", True),
        ("Own-half turnovers per 90", r["turnovers_own_half_90"], s["turnovers_own_half_90"], "{:.1f}", False),
        ("Presses per 90", r["presses_90"], s["presses_90"], "{:.1f}", None),
        ("Crosses per 90", r["crosses_90"], s["crosses_90"], "{:.1f}", None),
        ("Long balls per 90", r["long_balls_90"], s["long_balls_90"], "{:.1f}", None),
        ("High block", r["high_block_pct"], s["high_block_pct"], "{:.0f}%", None),
        ("Low block", r["low_block_pct"], s["low_block_pct"], "{:.0f}%", None),
    ]


def write_csvs(out, cfg, moments):
    data = out / "data"
    data.mkdir(exist_ok=True)
    with open(data / "moments.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["game", "team", "type", "detail", "goal", "half", "minute", "film_time"])
        for m in moments:
            w.writerow([m["game"], m["team"], m["type"], m["detail"], m["goal"], m["half"], m["minute"], m["film"]])
    with open(data / "frames.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["game", "film_time", "half", "minute", "source", "view", "possession", "ball_zone_x", "ball_zone_y",
                    "analyzed_block", "other_block", "players", "confidence", "note"])
        for g in cfg["games"]:
            names = {"analyzed_team": g["analyzed_team_name"], "other_team": g["other_team_name"]}
            for e in json.loads((config.LOGS_DIR / f"{g['id']}.json").read_text()):
                z = e.get("ball_zone") or [None, None]
                w.writerow([g["id"], e["timestamp"], e["half"], round(e.get("game_minute") or 0, 1), e["source"],
                            e["view"], names.get(e["possession"], e["possession"]), z[0], z[1],
                            e.get("analyzed_team_block"), e.get("other_team_block"), " ".join(e.get("players", [])),
                            e["confidence"], e.get("note", "")])
    for g in cfg["games"]:
        shutil.copy(config.LOGS_DIR / f"{g['id']}.json", data / f"{g['id']}.json")


def build(slug):
    cfg = config.load_config()
    m = cfg["matchup"]
    out = PAGE_DIR / slug
    out.mkdir(parents=True, exist_ok=True)
    store = Media(out, cfg["games"])
    others = [g["other_team_name"] for g in cfg["games"] if g["other_team_name"] not in (m["our_team"], m["opponent"])]
    names = [m["our_team"], m["opponent"], *others]
    moments, by_key = collect_moments(cfg, names, store)
    colors = {m["our_team"]: theme.US, m["opponent"]: theme.THEM}
    roles = {m["our_team"]: "Your team", m["opponent"]: "Opponent"}
    teams = [team_block(cfg, n, colors.get(n, theme.MUTED), roles.get(n, "In the film"), store, by_key) for n in names]
    us, them = teams[0], teams[1]
    plan = game_plan(team_profile(cfg, m["our_team"]), team_profile(cfg, m["opponent"]))
    pairs = [{"title": x["title"], "matches": x.get("matches", [])} for x in plan.get("exploit", []) + plan.get("counter", [])
             if x.get("matches")]
    games = [{"id": g["id"], "title": f"{g['analyzed_team_name']} vs {g['other_team_name']}", "score": g.get("final_score"),
              "analyzed": g["analyzed_team_name"], "other": g["other_team_name"],
              "minutes": next((t["kpis"]["minutes"] for t in teams if t["name"] == g["analyzed_team_name"]), None),
              "notes": g.get("notes", "")} for g in cfg["games"]]
    data = {
        "title": f"{m['our_team']} vs {m['opponent']}", "updated": date.today().isoformat(),
        "us": m["our_team"], "them": m["opponent"], "teams": teams, "games": games,
        "h2h": head_to_head(us, them), "pairs": pairs, "moments": moments,
    }
    (out / "data.js").write_text("window.SCOUT = " + json.dumps(data, separators=(",", ":")) + ";\n")
    for name in ("index.html", "app.js", "style.css"):
        shutil.copy(TEMPLATE / name, out / name)
    write_csvs(out, cfg, moments)
    clips = sum(1 for m in moments if m["clip"])
    frames = sum(1 for m in moments if m["frame"])
    print(f"Built website/games/{slug}/: {len(moments)} moments, {frames} frames, {clips} clips")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "game")
