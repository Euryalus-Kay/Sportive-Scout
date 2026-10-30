"""Interactive charts for the app (Plotly): hover for details, click shots.

Same rules as visualize.py (which draws the PNGs for reports): the analyzed
team always attacks left -> right and their left touchline is at the top.
"""
import math

import numpy as np
import plotly.graph_objects as go

from src.aggregate import TIMELINE_BINS, TIMELINE_STEP, share, timeline_bin
from src.ui.theme import BORDER, FONT, INK, MUTED, THEM, US
from src.visualize import POSITION_GROUPS, formation_positions, parse_shape, position_group

LENGTH, WIDTH = 105, 68
PITCH_FILL, PITCH_LINE = "#f6f8f5", "#cfd6cc"
GROUP_COLORS = {"FWD": US, "MID": THEM, "DEF": "#1baf7a"}
CONFIG = {"displayModeBar": False}


def _layout(fig, height, title=None):
    fig.update_layout(
        height=height, margin={"l": 6, "r": 6, "t": 40 if title else 6, "b": 6},
        paper_bgcolor="white", plot_bgcolor="white", showlegend=False,
        font={"family": FONT, "size": 12, "color": INK},
        title={"text": title, "x": 0.01, "xanchor": "left", "font": {"size": 14}} if title else None,
        hoverlabel={"bgcolor": "white", "bordercolor": BORDER, "font": {"family": FONT, "size": 12, "color": INK}},
    )
    return fig


# ---------- the pitch ----------

def _arc(cx, cy, r, start, end, steps=24):
    """SVG path points along a circle (Plotly shapes have no arc command)."""
    pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
           for a in np.linspace(start, end, steps)]
    return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts)


def pitch(height=420, title=None):
    """An empty pitch with locked proportions."""
    fig = go.Figure()
    line = {"color": PITCH_LINE, "width": 1.6}
    shapes = [dict(type="rect", x0=0, y0=0, x1=LENGTH, y1=WIDTH, line=line, fillcolor=PITCH_FILL, layer="below"),
              dict(type="line", x0=LENGTH / 2, y0=0, x1=LENGTH / 2, y1=WIDTH, line=line),
              dict(type="circle", x0=LENGTH / 2 - 9.15, y0=WIDTH / 2 - 9.15, x1=LENGTH / 2 + 9.15,
                   y1=WIDTH / 2 + 9.15, line=line)]
    for x0, sign in ((0, 1), (LENGTH, -1)):
        shapes += [dict(type="rect", x0=x0, y0=WIDTH / 2 - 20.16, x1=x0 + sign * 16.5, y1=WIDTH / 2 + 20.16, line=line),
                   dict(type="rect", x0=x0, y0=WIDTH / 2 - 9.16, x1=x0 + sign * 5.5, y1=WIDTH / 2 + 9.16, line=line),
                   dict(type="path", path=_arc(x0 + sign * 11, WIDTH / 2, 9.15,
                                               -53 if sign == 1 else 127, 53 if sign == 1 else 233), line=line)]
    for shape in shapes:
        shape.setdefault("layer", "above")
    fig.update_layout(shapes=shapes)
    fig.update_xaxes(range=[-2, LENGTH + 2], visible=False, fixedrange=True)
    fig.update_yaxes(range=[WIDTH + 2, -2], visible=False, fixedrange=True, scaleanchor="x", scaleratio=1)
    fig.add_annotation(x=LENGTH / 2, y=WIDTH + 1.2, text="attacking direction  →", showarrow=False,
                       font={"size": 10, "color": MUTED}, yanchor="top")
    return _layout(fig, height, title)


# ---------- maps ----------

def heat_map(grid, title=None, color=US, height=420):
    """Share of frames in each of the 24 zones, colored and written in."""
    fig = pitch(height, title)
    total = grid.sum()
    if not total:
        return _empty(fig, "Nothing logged yet")
    pct = 100 * grid / total
    xs = [(c + 0.5) * LENGTH / 6 for c in range(6)]
    ys = [(r + 0.5) * WIDTH / 4 for r in range(4)]
    fig.add_trace(go.Heatmap(
        z=pct, x=xs, y=ys, zmin=0, zmax=max(pct.max(), 1), xgap=2, ygap=2, showscale=False,
        colorscale=[[0, "rgba(255,255,255,0)"], [1, color]], opacity=0.9,
        text=[[f"{v:.0f}%" for v in row] for row in pct], texttemplate="%{text}",
        textfont={"size": 12, "color": INK}, customdata=grid,
        hovertemplate="%{text} of frames (%{customdata:.0f})<extra></extra>"))
    return fig


def count_map(events, title=None, color=THEM, height=420):
    """Where events happened (e.g. turnovers), by zone."""
    grid = np.zeros((4, 6))
    for e in events:
        if e.get("zone"):
            grid[e["zone"][1] - 1, e["zone"][0] - 1] += 1
    return heat_map(grid, title, color, height)


def shot_map(shots, title=None, against=False, height=420):
    """One marker per shot. Star = goal, filled = on target, ring = off target or blocked.

    Each point carries its moment (game id, video seconds) so a click can show the film.
    """
    fig = pitch(height, title)
    placed = [s for s in shots if s.get("xy")]
    if not placed:
        return _empty(fig, "No shots with a known spot yet" if shots else "No shots logged")
    for outcome, symbol, size in (("off", "circle-open", 13), ("on_target", "circle", 13), ("goal", "star", 22)):
        group = [s for s in placed if _outcome_group(s) == outcome]
        if not group:
            continue
        colors = ["#9ca3af" if against else GROUP_COLORS.get(position_group(s.get("position")), "#9ca3af")
                  for s in group]
        fig.add_trace(go.Scatter(
            x=[s["xy"][0] * LENGTH / 100 for s in group], y=[s["xy"][1] * WIDTH / 100 for s in group],
            mode="markers", marker={"symbol": symbol, "size": size, "color": colors,
                                    "line": {"width": 2 if symbol == "circle-open" else 1.2,
                                             "color": colors if symbol == "circle-open" else "white"}},
            customdata=[[s.get("timestamp"), _minute(s.get("game_minute")), s.get("position") or "unknown",
                         (s.get("outcome") or "unknown").replace("_", " "),
                         (s.get("build_up") or "unknown").replace("_", " "), s.get("game_id"),
                         s.get("video_seconds")] for s in group],
            hovertemplate=("<b>%{customdata[3]}</b> · %{customdata[1]}<br>Shooter: %{customdata[2]}"
                           "<br>Build-up: %{customdata[4]}<br>Film time %{customdata[0]}<extra></extra>")))
    if not against:
        for key, (name, _) in POSITION_GROUPS.items():
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name=name,
                                     marker={"size": 10, "color": GROUP_COLORS[key]}))
        fig.update_layout(showlegend=True, legend={"orientation": "h", "y": -0.02, "x": 0.5, "xanchor": "center",
                                                   "font": {"size": 11, "color": MUTED}})
    return fig


def _outcome_group(shot):
    return shot.get("outcome") if shot.get("outcome") in ("goal", "on_target") else "off"


def _minute(m):
    return f"{int(m) + 1}'" if m is not None else "?"


def formation(shape, block=None, title=None, color=US, height=420):
    """Dots with position labels for a shape like "4-3-3"."""
    fig = pitch(height, title)
    spots = formation_positions(shape, block)
    if not spots:
        return _empty(fig, "No clear formation logged yet")
    fig.add_trace(go.Scatter(
        x=[x * LENGTH / 100 for x, _, _ in spots], y=[y * WIDTH / 100 for _, y, _ in spots],
        mode="markers+text", text=[label for _, _, label in spots], textposition="bottom center",
        textfont={"size": 11, "color": INK}, marker={"size": 20, "color": color, "line": {"width": 2.5, "color": "white"}},
        hovertemplate="%{text}<extra></extra>"))
    fig.add_annotation(x=0, y=-1.2, xanchor="left", yanchor="bottom", showarrow=False,
                       text=f"<b>{shape}</b>" + (f" · {block} block" if block else ""),
                       font={"size": 12, "color": INK})
    return fig


def _empty(fig, message):
    fig.add_annotation(x=LENGTH / 2, y=WIDTH / 2, text=message, showarrow=False,
                       font={"size": 13, "color": MUTED})
    return fig


# ---------- time and bars ----------

def bin_labels():
    return [f"{i * TIMELINE_STEP}-{(i + 1) * TIMELINE_STEP}'" if i < TIMELINE_BINS - 1 else "90+'"
            for i in range(TIMELINE_BINS)]


def possession_by_bin(profile):
    """Possession % in each 5-minute bin (None where nothing was logged)."""
    t = profile["timeline"]
    total = t[:, 0] + t[:, 1]
    return [100 * a / n if n else None for a, n in zip(t[:, 0], total)]


def momentum(profile, color=US, height=300):
    """Who had the ball, 5 minutes at a time: up = this team, down = their opponent."""
    fig = go.Figure()
    poss = possession_by_bin(profile)
    if not any(v is not None for v in poss):
        fig.add_annotation(text="Nothing logged yet", showarrow=False, font={"size": 13, "color": MUTED})
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return _layout(fig, height)
    labels, t = bin_labels(), profile["timeline"]
    shots_for = _per_bin(profile["shots_for"])
    shots_against = _per_bin(profile["shots_against"])
    values = [(v - 50) if v is not None else 0 for v in poss]
    fig.add_trace(go.Bar(
        x=labels, y=values, base=50, marker={"color": [color if v >= 0 else "#c7cbd1" for v in values]},
        customdata=[[f"{v:.0f}%" if v is not None else "no frames", int(t[i, 2]), shots_for[i], shots_against[i]]
                    for i, v in enumerate(poss)],
        hovertemplate=("<b>%{x}</b><br>Ball: %{customdata[0]}<br>Frames in the final third: %{customdata[1]}"
                       "<br>Shots: %{customdata[2]} taken, %{customdata[3]} conceded<extra></extra>")))
    for shots, y, mcolor in ((profile["shots_for"], 106, color), (profile["shots_against"], -6, "#9ca3af")):
        pts = [s for s in shots if s.get("game_minute") is not None]
        if pts:
            fig.add_trace(go.Scatter(
                x=[labels[timeline_bin(s["game_minute"])] for s in pts], y=[y] * len(pts), mode="markers",
                marker={"symbol": ["star" if s.get("outcome") == "goal" else "circle" for s in pts],
                        "size": [16 if s.get("outcome") == "goal" else 8 for s in pts], "color": mcolor,
                        "line": {"width": 1, "color": "white"}},
                customdata=[[_minute(s["game_minute"]), (s.get("outcome") or "shot").replace("_", " ")] for s in pts],
                hovertemplate="%{customdata[1]} at %{customdata[0]}<extra></extra>", cliponaxis=False))
    fig.add_hline(y=50, line={"color": BORDER, "width": 1})
    fig.update_yaxes(range=[-12, 112], tickvals=[0, 50, 100], ticktext=["0%", "50%", "100%"],
                     gridcolor="#f3f4f6", fixedrange=True, tickfont={"size": 10, "color": MUTED})
    fig.update_xaxes(fixedrange=True, tickfont={"size": 10, "color": MUTED}, tickangle=0,
                     tickvals=labels[::3], ticktext=[label.split("-")[0].rstrip("'") + "'" for label in labels[::3]])
    fig.update_layout(bargap=0.25)
    return _layout(fig, height)


def _per_bin(shots):
    counts = [0] * TIMELINE_BINS
    for s in shots:
        if s.get("game_minute") is not None:
            counts[timeline_bin(s["game_minute"])] += 1
    return counts


def bars(counts, color=US, percent=False, height=None):
    """Horizontal bars, biggest on top, value at the end."""
    items = sorted(((str(k), v) for k, v in counts.items() if k), key=lambda kv: kv[1])
    fig = go.Figure()
    if not items:
        fig.add_annotation(text="Nothing logged yet", showarrow=False, font={"size": 13, "color": MUTED})
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return _layout(fig, height or 160)
    labels, values = zip(*items)
    fig.add_trace(go.Bar(x=values, y=labels, orientation="h", marker={"color": color},
                         text=[f"{v:.0f}%" if percent else f"{v:g}" for v in values], textposition="outside",
                         cliponaxis=False, hovertemplate="%{y}: %{text}<extra></extra>"))
    fig.update_xaxes(visible=False, range=[0, max(values) * 1.25 or 1], fixedrange=True)
    fig.update_yaxes(fixedrange=True, tickfont={"size": 12})
    return _layout(fig, height or max(140, 40 * len(items) + 30))


def shapes_seen(counter, color=US):
    """Top formations as a share of frames that had a readable shape."""
    pct = {s: share(counter, s) for s in counter if parse_shape(s)}
    return bars(dict(sorted(pct.items(), key=lambda kv: -kv[1])[:5]), color, percent=True)
