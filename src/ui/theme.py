"""The app's look: colors, CSS and small HTML building blocks.

The style follows clean data products like Polymarket: a white page, cards
with hairline borders, big bold numbers, thin two-color bars, one blue
accent, small gray labels in sentence case, and no decoration. Charts use the
same colors (see charts.py).
"""
import html

import streamlit as st

US, THEM = "#1652f0", "#eb6834"         # our team / the opponent
GOOD, BAD = "#16a34a", "#e23b3b"
INK, MUTED, BORDER, SOFT = "#0e1116", "#6e7681", "#e6e8ec", "#f5f6f8"
FONT = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
.block-container {{ padding-top: 4.4rem; padding-bottom: 3rem; max-width: 1240px; }}
div[class*="st-key-card"] {{ background: #fff; border-radius: 12px; }}
[data-testid="stMetric"] {{ background: #fff; border-radius: 12px; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: .8rem; font-weight: 500; }}
[data-testid="stMetricValue"] {{ font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -.01em; }}
.pm-label {{ color: {MUTED}; font-size: .8rem; font-weight: 500; }}
.pm-title {{ color: {INK}; font-size: 1rem; font-weight: 600; margin: 1px 0 12px; }}
.pm-h1 {{ color: {INK}; font-size: 1.65rem; font-weight: 700; letter-spacing: -.015em; line-height: 1.2; }}
.pm-sub {{ color: {MUTED}; font-size: .85rem; margin-top: 4px; }}
.pm-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 8px; vertical-align: 1px; }}
.pm-chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }}
.pm-chip {{ padding: 3px 10px; border-radius: 999px; background: {SOFT}; color: #3d444d; font-size: .75rem; font-weight: 500; }}
.pm-chip.warn {{ background: #fff4e5; color: #8a4b08; }}
.pm-tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }}
.pm-tile {{ border: 1px solid {BORDER}; border-radius: 12px; padding: 14px 16px; background: #fff; }}
.pm-tile .pm-label {{ margin-bottom: 8px; }}
.pm-pair {{ display: flex; justify-content: space-between; align-items: baseline; }}
.pm-num {{ font-size: 1.6rem; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -.02em; color: {INK}; }}
.pm-bar {{ display: flex; gap: 3px; height: 6px; margin-top: 10px; }}
.pm-bar span {{ display: block; height: 6px; border-radius: 3px; }}
.pm-rows {{ display: flex; flex-direction: column; }}
.pm-row {{ display: grid; grid-template-columns: 64px 1fr 64px; align-items: center; padding: 10px 0;
           border-bottom: 1px solid #f0f1f3; }}
.pm-row:last-child {{ border-bottom: none; }}
.pm-row .v {{ font-weight: 600; font-size: .92rem; font-variant-numeric: tabular-nums; color: #3d444d; }}
.pm-row .v.r {{ text-align: right; }}
.pm-row .v.lead {{ color: var(--c); font-weight: 700; }}
.pm-row .n {{ text-align: center; font-size: .84rem; color: {MUTED}; }}
.pm-row .pm-bar {{ grid-column: 1 / 4; margin-top: 8px; height: 4px; }}
.pm-row .pm-bar span {{ height: 4px; }}
.pm-insight {{ border: 1px solid {BORDER}; border-radius: 12px; padding: 14px 16px; background: #fff; margin-bottom: 10px; }}
.pm-insight .pm-num {{ color: var(--c); }}
.pm-insight .t {{ color: {INK}; font-size: .9rem; margin-top: 2px; }}
.pm-insight .m {{ color: {MUTED}; font-size: .78rem; margin-top: 6px; }}
.pm-insight .track {{ height: 4px; background: {SOFT}; border-radius: 3px; margin-top: 10px; }}
.pm-insight .track span {{ display: block; height: 4px; border-radius: 3px; background: var(--c); }}
.pm-li {{ display: grid; grid-template-columns: 62px 1fr 64px; align-items: center; gap: 12px; padding: 10px 2px;
          border-bottom: 1px solid #f0f1f3; }}
.pm-li .pm-num {{ font-size: 1.25rem; color: var(--c); }}
.pm-li .t {{ color: {INK}; font-size: .9rem; }}
.pm-li .m {{ color: {MUTED}; font-size: .76rem; margin-top: 2px; }}
.pm-li .track {{ height: 4px; background: {SOFT}; border-radius: 3px; }}
.pm-li .track span {{ display: block; height: 4px; border-radius: 3px; background: var(--c); }}
.pm-pairrow {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 10px 0; border-bottom: 1px solid #f0f1f3; }}
.pm-pairrow:last-child {{ border-bottom: none; }}
.pm-pairrow .pm-num {{ font-size: 1.25rem; color: var(--c); }}
.pm-pairrow .t {{ color: {INK}; font-size: .88rem; }}
.pm-pairrow .m {{ color: {MUTED}; font-size: .76rem; margin-top: 2px; }}
.pm-facts {{ display: flex; flex-direction: column; }}
.pm-fact {{ display: flex; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid #f0f1f3; font-size: .88rem; }}
.pm-fact:last-child {{ border-bottom: none; }}
.pm-fact span:first-child {{ color: {MUTED}; }}
.pm-fact span:last-child {{ color: {INK}; font-weight: 600; font-variant-numeric: tabular-nums; }}
.pm-empty {{ text-align: center; padding: 28px 12px; color: {MUTED}; font-size: .9rem; }}
.pm-status {{ display: flex; flex-direction: column; gap: 6px; font-size: .8rem; color: #3d444d; }}
.pm-status span::before {{ content: ""; display: inline-block; width: 7px; height: 7px; border-radius: 50%;
                           margin-right: 8px; background: var(--c); vertical-align: 1px; }}
.pm-step {{ display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px;
            border-radius: 6px; background: {INK}; color: #fff; font-weight: 600; font-size: .78rem; margin-right: 10px; }}
</style>
"""


def apply():
    """Load the app's styles (once per page run)."""
    st.session_state["_cards"] = 0
    st.html(CSS)


def esc(text):
    return html.escape(str(text))


def card():
    """A white card with a hairline border (a bordered container with a stable key for the CSS)."""
    st.session_state["_cards"] = st.session_state.get("_cards", 0) + 1
    return st.container(border=True, key=f"card_{st.session_state['_cards']}")


def heading(label, title=None):
    """Small gray label and an optional title, at the top of a card."""
    st.html(f'<div class="pm-label">{esc(label)}</div>'
            + (f'<div class="pm-title">{esc(title)}</div>' if title else ""))


def page_title(label, title, color=None):
    dot = f'<span class="pm-dot" style="background:{color}"></span>' if color else ""
    st.html(f'<div class="pm-label">{esc(label)}</div><div class="pm-h1">{dot}{esc(title)}</div>')


def chips(items):
    """Small rounded notes: [(text, tone)] with tone "" or "warn"."""
    if items:
        st.html('<div class="pm-chips">' + "".join(f'<span class="pm-chip {tone}">{esc(text)}</span>'
                                                  for text, tone in items) + "</div>")


def duel_tiles(items):
    """Market-style tiles: label, both numbers, a thin two-color bar. items: (label, a, b, fmt)."""
    tiles = []
    for name, a, b, fmt in items:
        total = (a + b) or 1
        tiles.append(f"""
        <div class="pm-tile"><div class="pm-label">{esc(name)}</div>
          <div class="pm-pair"><span class="pm-num" style="color:{US}">{fmt.format(a)}</span>
                               <span class="pm-num" style="color:{THEM}">{fmt.format(b)}</span></div>
          <div class="pm-bar"><span style="flex:{a / total:.3f};background:{US}"></span>
                              <span style="flex:{b / total:.3f};background:{THEM}"></span></div>
        </div>""")
    st.html(f'<div class="pm-tiles">{"".join(tiles)}</div>')


def compare_rows(rows):
    """value | label | value rows with a thin split bar. rows: (label, a, b, fmt, higher_is_better or None)."""
    out = ['<div class="pm-rows">']
    for name, a, b, fmt, higher_better in rows:
        lead_a = higher_better is not None and ((a > b) if higher_better else (a < b))
        lead_b = higher_better is not None and ((b > a) if higher_better else (b < a))
        total = (a + b) or 1
        out.append(f"""
        <div class="pm-row">
          <span class="v {'lead' if lead_a else ''}" style="--c:{US}">{fmt.format(a)}</span>
          <span class="n">{esc(name)}</span>
          <span class="v r {'lead' if lead_b else ''}" style="--c:{THEM}">{fmt.format(b)}</span>
          <div class="pm-bar"><span style="flex:{a / total:.3f};background:{US}"></span>
                              <span style="flex:{b / total:.3f};background:{THEM}"></span></div>
        </div>""")
    st.html("".join(out) + "</div>")


def legend(us_name, them_name):
    st.html(f'<div class="pm-pair" style="font-size:.82rem;font-weight:600;margin-bottom:2px">'
            f'<span><span class="pm-dot" style="background:{US}"></span>{esc(us_name)}</span>'
            f'<span>{esc(them_name)}<span class="pm-dot" style="background:{THEM};margin:0 0 0 8px"></span></span></div>')


def insight(f, color):
    """One insight: the number, what it measures, and what it is based on."""
    track = ""
    if f["stat"].endswith("%"):
        width = max(0.0, min(100.0, float(f["stat"].rstrip("%"))))
        track = f'<div class="track"><span style="width:{width:.0f}%"></span></div>'
    st.html(f"""
    <div class="pm-insight" style="--c:{color}">
      <div class="pm-num">{esc(f['stat'])}</div>
      <div class="t">{esc(f['label'])}</div>{track}
      <div class="m">{esc(f['basis'])} · {esc(f['evidence'])}</div>
    </div>""")


def insight_row(f, color):
    """One insight as a compact list row: number, line and basis, and a thin bar for percentages."""
    track = ""
    if f["stat"].endswith("%"):
        width = max(0.0, min(100.0, float(f["stat"].rstrip("%"))))
        track = f'<div class="track"><span style="width:{width:.0f}%"></span></div>'
    st.html(f'<div class="pm-li" style="--c:{color}"><span class="pm-num">{esc(f["stat"])}</span>'
            f'<div><div class="t">{esc(f["label"])}</div><div class="m">{esc(f["basis"])} · {esc(f["evidence"])}'
            f'</div></div><div>{track}</div></div>')


def pair_rows(pairs, left_color, right_color):
    """One finding on the left and the related findings stacked on the right: [(left, [rights])]."""
    cell = lambda f, c: (f'<div style="--c:{c};margin-bottom:6px"><span class="pm-num">{esc(f["stat"])}</span> '
                         f'<span class="t">{esc(f["label"])}</span><div class="m">{esc(f["basis"])} · '
                         f'{esc(f["evidence"])}</div></div>')
    st.html("".join(f'<div class="pm-pairrow">{cell(a, left_color)}<div>{"".join(cell(b, right_color) for b in bs)}'
                    f'</div></div>' for a, bs in pairs))


def facts(items):
    """A two-column list of (label, value)."""
    st.html('<div class="pm-facts">' + "".join(f'<div class="pm-fact"><span>{esc(k)}</span><span>{esc(v)}</span></div>'
                                              for k, v in items) + "</div>")


def empty(message):
    st.html(f'<div class="pm-empty">{esc(message)}</div>')


def step(number, title):
    st.html(f'<div style="display:flex;align-items:center;margin:2px 0 6px">'
            f'<span class="pm-step">{number}</span><span class="pm-title" style="margin:0">{esc(title)}</span></div>')


def status(lines):
    """Small status lines with a colored dot: [(text, color)]."""
    st.html('<div class="pm-status">' + "".join(f'<span style="--c:{c}">{esc(t)}</span>' for t, c in lines)
            + "</div>")
