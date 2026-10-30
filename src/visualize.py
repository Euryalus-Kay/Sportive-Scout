"""Field drawings and charts (matplotlib).

Every drawing shows the analyzed team attacking left -> right, with their
left touchline at the top. Each function returns a matplotlib Figure; the
interface shows it and `save_all` writes PNGs to reports/.

Figures are built with matplotlib's Figure class directly (not pyplot), so
the app can draw for several people at the same time safely.
"""
import re

import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Arc, Circle, Rectangle

from src.aggregate import TIMELINE_BINS, TIMELINE_STEP, share, timeline_bin
from src.positions import (POSITION_GROUPS, formation_positions, line_labels,  # noqa: F401
                           parse_shape, position_group)

# Colors (same as the app: white page, one blue accent, orange for the opponent)
SURFACE = "#ffffff"
LINE = "#d9dde3"
TEXT = "#0e1116"
TEXT_2 = "#6e7681"
BLUE, ORANGE, AQUA = "#1652f0", "#eb6834", "#16a34a"
GRAY = "#9aa1aa"
BLUES = LinearSegmentedColormap.from_list("blues", ["#eef3fe", "#9db6f8", "#1652f0", "#0b2e8a"])
ORANGES = LinearSegmentedColormap.from_list("oranges", ["#fdf0ea", "#f2a07f", "#eb6834", "#8a3410"])

LENGTH, WIDTH = 105, 68     # pitch size in meters, for drawing


def to_pitch(x, y):
    """0-100 relative coordinates -> drawing coordinates."""
    return x * LENGTH / 100, y * WIDTH / 100


def new_figure(width, height):
    """An empty figure on the app's background color."""
    fig = Figure(figsize=(width, height))
    fig.patch.set_facecolor(SURFACE)
    return fig


# ---------- the field ----------

def draw_pitch(ax):
    """Draw field markings; y grows downward so the team's left is on top."""
    ax.set_facecolor(SURFACE)
    kw = {"fill": False, "edgecolor": LINE, "linewidth": 1.2}
    ax.add_patch(Rectangle((0, 0), LENGTH, WIDTH, **kw))
    ax.plot([LENGTH / 2] * 2, [0, WIDTH], color=LINE, linewidth=1.2)
    ax.add_patch(Circle((LENGTH / 2, WIDTH / 2), 9.15, **kw))
    for x0, sign in ((0, 1), (LENGTH, -1)):
        ax.add_patch(Rectangle((x0, WIDTH / 2 - 20.16), sign * 16.5, 40.32, **kw))
        ax.add_patch(Rectangle((x0, WIDTH / 2 - 9.16), sign * 5.5, 18.32, **kw))
        ax.add_patch(Arc((x0 + sign * 11, WIDTH / 2), 18.3, 18.3,
                         theta1=-53 if sign == 1 else 127, theta2=53 if sign == 1 else 233,
                         edgecolor=LINE, linewidth=1.2))
    ax.set_xlim(-3, LENGTH + 3)
    ax.set_ylim(WIDTH + 3, -3)
    ax.set_aspect("equal")
    ax.axis("off")


def _figure(title=None):
    fig = new_figure(8, 5.6)
    ax = fig.add_subplot()
    draw_pitch(ax)
    if title:
        ax.set_title(title, color=TEXT, fontsize=12, loc="left", pad=10)
    ax.annotate("attacking direction", xy=(LENGTH * 0.62, WIDTH + 2.2),
                xytext=(LENGTH * 0.38, WIDTH + 2.2), color=TEXT_2, fontsize=8,
                va="center", arrowprops={"arrowstyle": "->", "color": TEXT_2})
    return fig, ax


# ---------- heat maps ----------

def heat_map(grid, title, cmap=BLUES, unit="% of frames"):
    """6x4 zone heat map with the share of frames written in each zone."""
    fig, ax = _figure(title)
    total = grid.sum()
    if total == 0:
        _empty(ax)
        return fig
    pct = 100 * grid / total
    ax.imshow(pct, cmap=cmap, extent=(0, LENGTH, WIDTH, 0), alpha=0.9,
              vmin=0, vmax=max(pct.max(), 1), zorder=0)
    zw, zh = LENGTH / 6, WIDTH / 4
    for row in range(4):
        for col in range(6):
            value = pct[row, col]
            dark = value > pct.max() * 0.55
            ax.text((col + 0.5) * zw, (row + 0.5) * zh, f"{value:.0f}%",
                    ha="center", va="center", fontsize=9,
                    color="white" if dark else TEXT_2)
    draw_pitch(ax)   # redraw lines on top of the colors
    ax.text(0, -1.5, unit, color=TEXT_2, fontsize=8)
    return fig


def count_map(events, title, cmap=ORANGES):
    """Heat map of where events happened (e.g. turnovers), by zone count."""
    grid = np.zeros((4, 6))
    for e in events:
        if e.get("zone"):
            x, y = e["zone"]
            grid[y - 1, x - 1] += 1
    return heat_map(grid, title, cmap=cmap, unit=f"{int(grid.sum())} events with a known zone")


# ---------- formation ----------

def formation_map(shape, block, title):
    """Dots for each position in the team's most common shape."""
    fig, ax = _figure(title)
    spots = formation_positions(shape, block)
    if not spots:
        _empty(ax, "No clear formation logged yet")
        return fig
    for x, y, label in spots:
        px, py = to_pitch(x, y)
        ax.add_patch(Circle((px, py), 2.6, facecolor=BLUE, edgecolor=SURFACE,
                            linewidth=2, zorder=3))
        ax.text(px, py + 5.2, label, ha="center", va="center", fontsize=9,
                color=TEXT, fontweight="bold", zorder=4)
    caption = shape + (f", {block} block" if block else "")
    ax.text(0, -1.5, caption, color=TEXT_2, fontsize=9)
    return fig


# ---------- shots ----------

def shot_map(shots, title, against=False):
    """Shots by spot. Color = shooter's position group, shape = outcome."""
    fig, ax = _figure(title)
    placed = [s for s in shots if s.get("xy")]
    if not shots:
        _empty(ax, "No shots logged")
        return fig
    for s in placed:
        px, py = to_pitch(*s["xy"])
        group = position_group(s.get("position"))
        color = GRAY if against or group is None else POSITION_GROUPS[group][1]
        if s.get("outcome") == "goal":
            ax.scatter(px, py, marker="*", s=320, color=color, edgecolor=SURFACE,
                       linewidth=1.5, zorder=4)
        elif s.get("outcome") == "on_target":
            ax.scatter(px, py, s=90, color=color, edgecolor=SURFACE, linewidth=2, zorder=3)
        else:
            ax.scatter(px, py, s=90, facecolor="none", edgecolor=color, linewidth=2, zorder=3)
    _shot_legend(ax, against)
    missing = len(shots) - len(placed)
    note = f"{len(shots)} shots, {sum(s.get('outcome') == 'goal' for s in shots)} goals"
    if missing:
        note += f" ({missing} without a known spot)"
    ax.text(0, -1.5, note, color=TEXT_2, fontsize=8)
    return fig


def _marker(label, color=TEXT_2, marker="o", filled=True, size=7):
    return Line2D([], [], linestyle="none", marker=marker, markersize=size, label=label,
                  markerfacecolor=color if filled else "none", markeredgecolor=color, markeredgewidth=1.5)


def _shot_legend(ax, against):
    handles = [_marker("Goal", marker="*", size=12), _marker("On target"),
               _marker("Off target / blocked", filled=False)]
    if not against:
        handles += [_marker(name, color=c) for name, c in POSITION_GROUPS.values()]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=3,
              frameon=False, fontsize=8, labelcolor=TEXT_2)


# ---------- simple bar charts ----------

def bar_chart(counts, title, xlabel, color=BLUE, as_percent=False):
    """Horizontal bars, biggest first, value written at the end of each bar."""
    items = [(k, v) for k, v in counts.items() if k]
    fig = new_figure(6, max(1.6, 0.5 * len(items) + 0.8))
    ax = fig.add_subplot()
    ax.set_facecolor(SURFACE)
    ax.set_title(title, color=TEXT, fontsize=12, loc="left")
    if not items:
        _empty(ax, "Nothing logged yet")
        ax.axis("off")
        return fig
    items.sort(key=lambda kv: kv[1])
    labels, values = zip(*items)
    ax.barh(labels, values, color=color, height=0.6, edgecolor=SURFACE, linewidth=2)
    for i, v in enumerate(values):
        ax.text(v, i, f" {v:.0f}%" if as_percent else f" {v}", va="center",
                fontsize=9, color=TEXT_2)
    ax.set_xlabel(xlabel, color=TEXT_2, fontsize=9)
    ax.tick_params(colors=TEXT_2, labelsize=9, length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xlim(0, max(max(values), 1) * 1.18)
    ax.xaxis.set_visible(False)
    fig.tight_layout()
    return fig


def side_chart(counter, title):
    """Left / center / right share as bars."""
    pct = {side.capitalize(): share(counter, side) for side in ("left", "center", "right")}
    return bar_chart(pct, title, "% of frames", as_percent=True)


def shape_chart(counter, title):
    """How often each formation was seen, as a share of frames with a shape."""
    pct = {shape: share(counter, shape) for shape in counter if parse_shape(shape)}
    top = dict(sorted(pct.items(), key=lambda kv: -kv[1])[:6])
    return bar_chart(top, title, "% of frames", as_percent=True)


def possession_chart(profile):
    """One bar split between the team and their opponent."""
    pct = profile.get("possession_pct")
    fig = new_figure(6, 1.3)
    ax = fig.add_subplot()
    ax.set_facecolor(SURFACE)
    ax.axis("off")
    ax.set_title("Possession", color=TEXT, fontsize=12, loc="left")
    if pct is None:
        _empty(ax, "Nothing logged yet")
        return fig
    ax.barh([0], [pct], color=BLUE, height=0.5, edgecolor=SURFACE, linewidth=2)
    ax.barh([0], [100 - pct], left=[pct], color=GRAY, height=0.5, edgecolor=SURFACE, linewidth=2)
    ax.text(1, 0, f"{profile['team']}  {pct:.0f}%", va="center", color="white", fontsize=9)
    ax.text(99, 0, f"Opponents  {100 - pct:.0f}%", va="center", ha="right", color=TEXT, fontsize=9)
    ax.set_xlim(0, 100)
    fig.tight_layout()
    return fig


# ---------- comparing the two teams ----------

COMPARISON = [  # (key in profile["rates"], label, is a percentage)
    ("possession", "Possession %", True),
    ("shots_90", "Shots per 90", False),
    ("shots_against_90", "Shots conceded per 90", False),
    ("on_target_pct", "Shots on target %", True),
    ("box_shots_pct", "Shots from inside the box %", True),
    ("final_third_pct", "Possession in the final third %", True),
    ("presses_90", "Presses per 90", False),
    ("crosses_90", "Crosses per 90", False),
    ("long_balls_90", "Long balls per 90", False),
    ("turnovers_own_half_90", "Turnovers in own half per 90", False),
    ("high_block_pct", "Defends with a high block %", True),
    ("low_block_pct", "Defends with a low block %", True),
]


def comparison_chart(us, them):
    """Butterfly chart: our numbers to the left, theirs to the right, row by row."""
    fig = new_figure(8, 0.42 * len(COMPARISON) + 1.2)
    ax = fig.add_subplot()
    ax.set_facecolor(SURFACE)
    ax.set_title(f"{us['team']} vs {them['team']}", color=TEXT, fontsize=12, loc="left")
    if not (us["frames_logged"] or them["frames_logged"]):
        _empty(ax, "Nothing logged yet")
        ax.axis("off")
        return fig
    for row, (key, label, pct) in enumerate(reversed(COMPARISON)):
        a, b = us["rates"][key], them["rates"][key]
        top = max(a, b, 1e-9)
        ax.barh(row, -a / top, color=BLUE, height=0.55)
        ax.barh(row, b / top, color=ORANGE, height=0.55)
        fmt = (lambda v: f"{v:.0f}%") if pct else (lambda v: f"{v:.1f}")
        ax.text(-a / top - 0.03, row, fmt(a), ha="right", va="center", fontsize=8, color=TEXT_2)
        ax.text(b / top + 0.03, row, fmt(b), ha="left", va="center", fontsize=8, color=TEXT_2)
        ax.text(0, row + 0.36, label, ha="center", va="bottom", fontsize=8, color=TEXT, zorder=3,
                bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1.5})
    ax.axvline(0, color=LINE, linewidth=1, zorder=1)
    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(-0.6, len(COMPARISON) - 0.1)
    ax.axis("off")
    ax.legend(handles=[_marker(us["team"], BLUE, "s"), _marker(them["team"], ORANGE, "s")],
              loc="upper center", bbox_to_anchor=(0.5, 0.0), ncol=2, frameon=False, fontsize=9,
              labelcolor=TEXT_2)
    fig.tight_layout()
    return fig


# ---------- the game, minute by minute ----------

def timeline_chart(profile):
    """Possession per 5 minutes (bars around 50%), with shots and goals on top."""
    fig = new_figure(8, 3.2)
    ax = fig.add_subplot()
    ax.set_facecolor(SURFACE)
    ax.set_title(f"{profile['team']}: the game, 5 minutes at a time", color=TEXT, fontsize=12, loc="left")
    t = profile["timeline"]
    poss = t[:, 0] + t[:, 1]
    if not poss.sum():
        _empty(ax, "Nothing logged yet")
        ax.axis("off")
        return fig
    share_in = np.divide(100 * t[:, 0], poss, out=np.full(TIMELINE_BINS, np.nan), where=poss > 0)
    x = np.arange(TIMELINE_BINS)
    colors = [BLUE if v >= 50 else ORANGE for v in np.nan_to_num(share_in, nan=50)]
    ax.bar(x, np.nan_to_num(share_in, nan=50) - 50, bottom=50, color=colors, width=0.75, alpha=0.85)
    ax.axhline(50, color=LINE, linewidth=1)
    for shots, y, color in ((profile["shots_for"], 104, BLUE), (profile["shots_against"], -4, GRAY)):
        for s in shots:
            if s.get("game_minute") is None:
                continue
            bin_x = timeline_bin(s["game_minute"]) + (s["game_minute"] % TIMELINE_STEP) / TIMELINE_STEP - 0.5
            goal = s.get("outcome") == "goal"
            ax.scatter(bin_x, y, marker="*" if goal else "o", s=150 if goal else 22, color=color,
                       edgecolor=SURFACE, linewidth=0.8, zorder=3, clip_on=False)
    ax.set_xticks(x, [f"{i * TIMELINE_STEP}'" if i < TIMELINE_BINS - 1 else "90+'" for i in x],
                  fontsize=7, color=TEXT_2)
    ax.set_yticks([0, 50, 100], ["0%", "50%", "100%"], fontsize=7, color=TEXT_2)
    ax.set_ylim(-8, 108)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.legend(handles=[_marker("More of the ball", BLUE, "s"), _marker("Less of the ball", ORANGE, "s"),
                       _marker("Shot taken (top)", BLUE), _marker("Shot conceded (bottom)", GRAY),
                       _marker("Goal", TEXT_2, "*", size=11)],
              loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=5, frameon=False, fontsize=7,
              labelcolor=TEXT_2)
    fig.tight_layout()
    return fig


def _empty(ax, message="Nothing logged yet"):
    ax.text(0.5, 0.5, message, transform=ax.transAxes, ha="center", va="center",
            color=TEXT_2, fontsize=11)


# ---------- everything for one team ----------

def team_figures(p):
    """All figures for a team profile, keyed by a short name."""
    name = p["team"]
    return {
        "formation_in": formation_map(p["formation_in"], None, f"{name}: shape with the ball"),
        "formation_out": formation_map(p["formation_out"], p["block_out_main"],
                                       f"{name}: shape without the ball"),
        "heat_all": heat_map(p["heat_all"], f"{name}: where the ball is (all frames)"),
        "heat_in": heat_map(p["heat_in"], f"{name}: ball location when they have it"),
        "heat_out": heat_map(p["heat_out"], f"{name}: ball location when opponents have it",
                             cmap=ORANGES),
        "shots_for": shot_map(p["shots_for"], f"{name}: shots taken"),
        "shots_against": shot_map(p["shots_against"], f"{name}: shots conceded", against=True),
        "turnovers": count_map(p["turnovers"], f"{name}: where they lose the ball"),
        "goals_by_position": bar_chart(p["goals_by_position"], f"{name}: goals by position", "goals"),
        "attack_side": side_chart(p["attack_side"], f"{name}: final-third attacks by side"),
        "possession": possession_chart(p),
        "timeline": timeline_chart(p),
    }


def save_all(p, out_dir):
    """Write every figure for a team as PNG. Returns {name: path}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(p["team"])
    paths = {}
    for key, fig in team_figures(p).items():
        path = out_dir / f"{slug}_{key}.png"
        fig.savefig(path, dpi=130, bbox_inches="tight", facecolor=SURFACE)
        paths[key] = path
    return paths


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
