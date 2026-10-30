"""Builds team reports and the game plan as markdown, with heat map PNGs.

Usage:
    python -m src.report            # real games from games.yaml
    python -m src.report --sample   # the fake demo games
"""
import argparse
import base64
import html
import io
from datetime import date

from src import config, sample_data
from src.aggregate import events_of, team_profile
from src.insights import game_plan, strengths, weaknesses, context_notes
from src.visualize import SURFACE, save_all, slugify, team_figures


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
    (reports_dir / "scouting_report.html").write_text(html_report(us, them, plan))
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


# ---------- printable HTML ----------

HTML_STYLE = """
body { font-family: Inter, -apple-system, 'Segoe UI', Roboto, sans-serif; color: #111827; background: #f3f4f6;
       margin: 0; padding: 32px 16px; }
main { max-width: 960px; margin: 0 auto; }
h1 { font-size: 28px; margin: 0 0 4px; } h2 { font-size: 20px; margin: 28px 0 10px; }
h3 { font-size: 15px; margin: 0 0 6px; }
.muted { color: #6b7280; font-size: 13px; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; padding: 16px 18px; margin: 12px 0;
        break-inside: avoid; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.item { border-left: 4px solid var(--tone); padding: 6px 12px; margin: 8px 0; }
.item p { margin: 2px 0; font-size: 14px; }
.chip { display: inline-block; background: #f3f4f6; border-radius: 999px; padding: 1px 9px; font-size: 12px;
        color: #374151; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
td { padding: 6px 4px; border-bottom: 1px solid #f1f2f4; } td.num { text-align: right; font-weight: 700; }
img { width: 100%; height: auto; }
@media (max-width: 700px) { .grid { grid-template-columns: 1fr; } }
@media print { body { background: #fff; padding: 0; } .card { border-color: #ddd; } }
"""


def html_report(us, them, plan):
    """One self-contained HTML page (charts embedded) to print or send to coaches."""
    e = lambda text: html.escape(str(text))
    out = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' "
           f"content='width=device-width, initial-scale=1'><title>Scouting report: {e(them['team'])}</title>"
           f"<style>{HTML_STYLE}</style></head><body><main>",
           f"<h1>{e(us['team'])} vs {e(them['team'])}</h1>",
           f"<div class='muted'>Sportive Scout report, {date.today():%B %d, %Y}. Every number comes from "
           f"logged game film; patterns marked 'seen once' are things to watch for, not facts.</div>"]
    if plan["context"]:
        out.append("<div class='card'>" + "".join(f"<p class='muted'>{e(n)}</p>" for n in plan["context"]) + "</div>")

    out.append("<h2>Game plan</h2><div class='grid'>")
    for title, items, tone in (("Attack their weaknesses", plan["exploit"], "#1baf7a"),
                               ("Stop their strengths", plan["counter"], "#eb6834")):
        out.append(f"<div class='card'><h3>{title}</h3>")
        for m in items or []:
            f = m["item"]
            out.append(f"<div class='item' style='--tone:{tone}'><p><b>{e(f['title'])}</b> "
                       f"<span class='chip'>{e(f['evidence'])}</span></p><p>{e(f['action'])}</p>"
                       + (f"<p class='muted'>Linked: {e('; '.join(m['matches']))}</p>" if m["matches"] else "")
                       + "</div>")
        if not items:
            out.append("<p class='muted'>Nothing clear enough yet.</p>")
        out.append("</div>")
    out.append("</div>")
    if plan["fix"]:
        out.append("<div class='card'><h3>Fix in training this week</h3>"
                   + "".join(f"<div class='item' style='--tone:#dc2626'><p><b>{e(w['title'])}</b></p>"
                             f"<p>{e(w['action'])}</p></div>" for w in plan["fix"]) + "</div>")
    out.append("<div class='grid'><div class='card'><h3>Set pieces</h3>"
               + "".join(f"<p>{e(n)}</p>" for n in plan["set_pieces"]) + "</div>"
               "<div class='card'><h3>First 10-15 minutes</h3>"
               + "".join(f"<p>&#9744; {e(c)}</p>" for c in plan["first_15"]) + "</div></div>")

    for p in (them, us):
        out.append(_team_html(p, e))
    out.append("</main></body></html>")
    return "\n".join(out)


def _team_html(p, e):
    """The section of the HTML report for one team."""
    figs = team_figures(p)
    poss = p["possession_pct"]
    rows = [("Minutes analyzed", f"{p['minutes_covered']:.0f}"),
            ("Possession", f"{poss:.0f}%" if poss is not None else "not logged"),
            ("Shots / goals", f"{len(p['shots_for'])} / {len(p['goals_for'])}"),
            ("Shots / goals conceded", f"{len(p['shots_against'])} / {len(p['goals_against'])}"),
            ("Shape with / without the ball", f"{p['formation_in'] or '?'} / {p['formation_out'] or '?'}"),
            ("Average confidence", f"{p['avg_confidence']:.2f}")]
    out = [f"<h2>{e(p['team'])}</h2><div class='card'><table>"
           + "".join(f"<tr><td>{e(k)}</td><td class='num'>{e(v)}</td></tr>" for k, v in rows) + "</table></div>"]
    out.append("<div class='grid'>")
    for title, items in (("Strengths", strengths(p)), ("Weaknesses", weaknesses(p))):
        out.append(f"<div class='card'><h3>{title}</h3>"
                   + ("".join(f"<p><b>{e(f['title'])}</b> <span class='chip'>{e(f['evidence'])}</span><br>"
                              f"<span class='muted'>{e(f['detail'])}</span></p>" for f in items)
                      or "<p class='muted'>Nothing clear enough yet.</p>") + "</div>")
    out.append("</div><div class='grid'>")
    for key in ("formation_out", "formation_in", "heat_in", "heat_out", "shots_for", "shots_against",
                "turnovers", "attack_side"):
        out.append(f"<div class='card'>{_img(figs[key])}</div>")
    out.append(f"</div><div class='card'>{_img(figs['timeline'])}</div>")
    return "".join(out)


def _img(fig):
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=110, bbox_inches="tight", facecolor=SURFACE)
    return f"<img alt='' src='data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}'>"


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
