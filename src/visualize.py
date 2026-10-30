"""Field drawings and charts (matplotlib).

Every drawing shows the analyzed team attacking left -> right, with their
left touchline at the top. Each function returns a matplotlib Figure; the
interface shows it and `save_all` writes PNGs to reports/.
"""
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Arc, Circle, Rectangle

from src.aggregate import share

# Colors (validated reference palette, light mode)
SURFACE = "#fcfcfb"
LINE = "#c9c8c2"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
GRAY = "#a3a29b"
BLUES = LinearSegmentedColormap.from_list("blues", ["#eef4fc", "#86b6ef", "#2a78d6", "#0d366b"])
ORANGES = LinearSegmentedColormap.from_list("oranges", ["#fdf0ea", "#f2a07f", "#eb6834", "#8a3410"])

LENGTH, WIDTH = 105, 68     # pitch size in meters, for drawing


def to_pitch(x, y):
    """0-100 relative coordinates -> drawing coordinates."""
    return x * LENGTH / 100, y * WIDTH / 100


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
    fig, ax = plt.subplots(figsize=(8, 5.6))
    fig.patch.set_facecolor(SURFACE)
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
    fig = heat_map(grid, title, cmap=cmap, unit=f"{int(grid.sum())} events with a known zone")
    return fig


# ---------- formation ----------

DEF_LABELS = {3: ["CB", "CB", "CB"], 4: ["LB", "CB", "CB", "RB"],
              5: ["LWB", "CB", "CB", "CB", "RWB"]}
MID_LABELS = {1: ["DM"], 2: ["CM", "CM"], 3: ["CM", "CM", "CM"],
              4: ["LM", "CM", "CM", "RM"], 5: ["LM", "CM", "CM", "CM", "RM"]}
FWD_LABELS = {1: ["ST"], 2: ["ST", "ST"], 3: ["LW", "ST", "RW"]}
BLOCK_SHIFT = {"low": -10, "mid": 0, "high": 10, None: 0}
LINE_SPREAD = {1: 0, 2: 34, 3: 56, 4: 72, 5: 80}   # how wide each line is, 0-100


def parse_shape(shape):
    """"4-2-3-1 high press" -> [4, 2, 3, 1]; None if no outfield numbers add to 10."""
    if not shape:
        return None
    lines = [int(n) for n in re.findall(r"\d", shape.split()[0])]
    return lines if sum(lines) == 10 and len(lines) >= 2 else None


def line_labels(count, index, n_lines):
    """Position labels for one line of the formation."""
    if index == 0:
        return DEF_LABELS.get(count, ["D"] * count)
    if index == n_lines - 1:
        return FWD_LABELS.get(count, ["F"] * count)
    if n_lines >= 4 and index == 1:
        return ["DM"] * count
    if n_lines >= 4 and index == n_lines - 2 and count == 3:
        return ["LW", "AM", "RW"]
    return MID_LABELS.get(count, ["M"] * count)


def formation_positions(shape, block=None):
    """[(x, y, label)] in 0-100 coordinates for a shape like "4-3-3"."""
    lines = parse_shape(shape)
    if not lines:
        return []
    shift = BLOCK_SHIFT.get(block, 0)
    spots = [(6, 50, "GK")]
    for i, count in enumerate(lines):
        x = 22 + i * (56 / (len(lines) - 1)) + shift
        labels = line_labels(count, i, len(lines))
        spread = LINE_SPREAD.get(count, 80)
        if "LW" in labels:
            spread = 68     # wingers stay wide
        for j in range(count):
            y = 50 if count == 1 else 50 - spread / 2 + j * spread / (count - 1)
            spots.append((x, y, labels[j]))
    return spots


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

POSITION_GROUPS = {"FWD": ("Forward", BLUE), "MID": ("Midfielder", ORANGE),
                   "DEF": ("Defender", AQUA)}
FORWARDS = {"ST", "CF", "F", "LW", "RW", "SS"}
DEFENDERS = {"CB", "LB", "RB", "LWB", "RWB", "D", "GK"}


def position_group(position):
    """Map a position label to Forward / Midfielder / Defender / None."""
    p = (position or "").upper()
    if p in FORWARDS:
        return "FWD"
    if p in DEFENDERS:
        return "DEF"
    if p and p != "UNKNOWN":
        return "MID"
    return None


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


def _shot_legend(ax, against):
    handles = [plt.scatter([], [], marker="*", s=160, color=TEXT_2, label="Goal"),
               plt.scatter([], [], s=50, color=TEXT_2, label="On target"),
               plt.scatter([], [], s=50, facecolor="none", edgecolor=TEXT_2, label="Off target / blocked")]
    if not against:
        handles += [plt.scatter([], [], s=50, color=c, label=name)
                    for name, c in POSITION_GROUPS.values()]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=3,
              frameon=False, fontsize=8, labelcolor=TEXT_2)


# ---------- simple bar charts ----------

def bar_chart(counts, title, xlabel, color=BLUE, as_percent=False):
    """Horizontal bars, biggest first, value written at the end of each bar."""
    items = [(k, v) for k, v in counts.items() if k]
    fig, ax = plt.subplots(figsize=(6, max(1.6, 0.5 * len(items) + 0.8)))
    fig.patch.set_facecolor(SURFACE)
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


def possession_chart(profile):
    """One bar split between the team and their opponent."""
    pct = profile.get("possession_pct")
    fig, ax = plt.subplots(figsize=(6, 1.3))
    fig.patch.set_facecolor(SURFACE)
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
    }


def save_all(p, out_dir):
    """Write every figure for a team as PNG. Returns {name: path}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(p["team"])
    paths = {}
    for key, fig in team_figures(p).items():
        path = out_dir / f"{slug}_{key}.png"
        fig.savefig(path, dpi=130, bbox_inches="tight", facecolor=SURFACE)
        plt.close(fig)
        paths[key] = path
    return paths


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
