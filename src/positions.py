"""Formations and positions: the pure helpers the app and the reports share.

Kept apart from visualize.py so the app (and its browser version) can use them
without loading matplotlib.
"""
import re

BLUE, ORANGE, AQUA = "#1652f0", "#eb6834", "#16a34a"

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
