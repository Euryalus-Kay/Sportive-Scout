"""Builds team reports and the game plan as markdown, with heat map PNGs.

Usage:
    python -m src.report            # real games from games.yaml
    python -m src.report --sample   # the fake demo games
"""
import argparse

from src import config, sample_data
from src.aggregate import events_of, team_profile
from src.insights import game_plan, strengths, weaknesses, context_notes
from src.visualize import save_all, slugify


def build(cfg, logs_dir, reports_dir):
    """Profiles -> PNGs -> markdown. Returns (us, them, plan)."""
    matchup = cfg["matchup"]
    us = team_profile(cfg, matchup["our_team"], logs_dir)
    them = team_profile(cfg, matchup["opponent"], logs_dir)
    images = reports_dir / "images"
    for p in (us, them):
        pngs = save_all(p, images)
        path = reports_dir / f"{slugify(p['team'])}_report.md"
        path.write_text(team_report(p, pngs, reports_dir))
    plan = game_plan(us, them)
    (reports_dir / "game_plan.md").write_text(game_plan_markdown(us, them, plan, images, reports_dir))
    return us, them, plan


# ---------- team report ----------

def team_report(p, pngs, reports_dir):
    img = lambda key: pngs[key].relative_to(reports_dir).as_posix()
    lines = [f"# {p['team']}: scouting report", ""]
    lines += [f"Analyzed {p['minutes_covered']:.0f} minutes ({p['frames_wide']} wide-view frames), "
              f"average confidence {p['avg_confidence']:.2f}.", ""]
    lines += _bullets("Game context", context_notes(p))

    lines += ["## Formation", "",
              f"- With the ball: **{p['formation_in'] or 'unclear'}**",
              f"- Without the ball: **{p['formation_out'] or 'unclear'}**"
              + (f", mostly a **{p['block_out_main']} block**" if p["block_out_main"] else ""),
              "", f"![shape with the ball]({img('formation_in')})",
              f"![shape without the ball]({img('formation_out')})", ""]

    poss = p["possession_pct"]
    lines += ["## Attacking patterns", "",
              f"- Possession: **{poss:.0f}%**" if poss is not None else "- Possession: not logged",
              f"- Shots: {len(p['shots_for'])}, goals: {len(p['goals_for'])}",
              "- Goals by position: " + (", ".join(f"{k} {v}" for k, v in p["goals_by_position"].items()) or "none"),
              f"- Crosses: {len(events_of(p['events_for'], 'cross'))}, "
              f"long balls: {len(events_of(p['events_for'], 'long_ball'))}",
              "", f"![ball when they have it]({img('heat_in')})",
              f"![shots]({img('shots_for')})", ""]

    lines += ["## Defensive patterns", "",
              f"- Turnovers logged: {len(p['turnovers'])}",
              f"- Shots conceded: {len(p['shots_against'])}, goals conceded: {len(p['goals_against'])}",
              "", f"![ball when opponents have it]({img('heat_out')})",
              f"![where they lose the ball]({img('turnovers')})",
              f"![shots conceded]({img('shots_against')})", ""]

    sp = events_of(p["events_for"], "set_piece")
    lines += ["## Set pieces", "", f"- Set pieces logged: {len(sp)}",
              f"- Corners: {len(events_of(p['events_for'], 'set_piece', subtype='corner'))}", ""]

    top = p["players"].most_common(5)
    lines += ["## Most-involved jersey numbers", "",
              ", ".join(f"#{n} ({c})" for n, c in top) if top else "No numbers were readable.", ""]

    lines += _findings("Strengths", strengths(p)) + _findings("Weaknesses", weaknesses(p))
    return "\n".join(lines)


def _findings(title, items):
    lines = [f"## {title}", ""]
    if not items:
        return lines + ["Nothing clear enough to call yet.", ""]
    for f in items:
        stamps = ", ".join(f["timestamps"]) or "from overall stats"
        lines += [f"- **{f['title']}** ({f['evidence']}). {f['detail']} Evidence: {stamps}"]
    return lines + [""]


def _bullets(title, items):
    if not items:
        return []
    return [f"**{title}:**", ""] + [f"- {i}" for i in items] + [""]


# ---------- game plan ----------

def game_plan_markdown(us, them, plan, images, reports_dir):
    rel = lambda team, key: (images / f"{slugify(team)}_{key}.png").relative_to(reports_dir).as_posix()
    lines = [f"# Game plan: {us['team']} vs {them['team']}", ""]
    lines += _bullets("Context to keep in mind", plan["context"])

    lines += ["## How to exploit their weaknesses", ""]
    for m in plan["exploit"] or []:
        w = m["item"]
        lines.append(f"- **{w['title']}** ({w['evidence']}): {w['action']}")
        if m["matches"]:
            lines.append(f"  - Fits our strength: {'; '.join(m['matches'])}")
    if not plan["exploit"]:
        lines.append("- No clear weaknesses yet; log more of their film.")

    lines += ["", "## How to counter their strengths", ""]
    for m in plan["counter"] or []:
        s = m["item"]
        lines.append(f"- **{s['title']}** ({s['evidence']}): {s['action']}")
        if m["matches"]:
            lines.append(f"  - Danger, this hits our weakness: {'; '.join(m['matches'])}")
    if not plan["counter"]:
        lines.append("- No clear strengths yet; log more of their film.")

    if plan["fix"]:
        lines += ["", "## Our weaknesses they could target", ""]
        lines += [f"- **{w['title']}**: fix this in training this week." for w in plan["fix"]]

    lines += ["", "## Set pieces", ""] + [f"- {n}" for n in plan["set_pieces"]]
    lines += ["", "## First 10-15 minutes checklist", ""] + [f"- [ ] {c}" for c in plan["first_15"]]

    lines += ["", "## Heat maps", "",
              f"![{them['team']} with the ball]({rel(them['team'], 'heat_in')})",
              f"![{them['team']} without the ball]({rel(them['team'], 'heat_out')})",
              f"![{us['team']} with the ball]({rel(us['team'], 'heat_in')})",
              f"![{us['team']} without the ball]({rel(us['team'], 'heat_out')})", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Build reports and the game plan.")
    parser.add_argument("--sample", action="store_true", help="use the fake demo games")
    args = parser.parse_args()
    if args.sample:
        sample_data.ensure()
        cfg = config.load_config(config.SAMPLE_GAMES_FILE)
        logs, reports = config.SAMPLE_LOGS_DIR, config.SAMPLE_REPORTS_DIR
    else:
        cfg = config.load_config()
        logs, reports = config.LOGS_DIR, config.REPORTS_DIR
    reports.mkdir(parents=True, exist_ok=True)
    us, them, _ = build(cfg, logs, reports)
    print(f"Reports written to {reports.relative_to(config.ROOT)}/ for {us['team']} and {them['team']}")


if __name__ == "__main__":
    main()
