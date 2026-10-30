"""The app's look: colors, CSS and small HTML building blocks.

The style is modeled on football match-centre pages like FotMob's: a soft
gray page, white rounded cards, one color per team, bold numbers, quiet
uppercase labels, and comparison rows where the team that leads is
highlighted. Charts use the same colors (see charts.py).
"""
import html

import streamlit as st

US, THEM = "#2a78d6", "#eb6834"         # our team / the opponent
GOOD, WARN, BAD = "#1baf7a", "#d97706", "#dc2626"
INK, MUTED, BORDER, SOFT = "#111827", "#6b7280", "#e5e7eb", "#f3f4f6"
FONT = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
.block-container {{ padding-top: 4.6rem; padding-bottom: 3rem; max-width: 1320px; }}
div[class*="st-key-card"] {{ background: #fff; border-radius: 16px; box-shadow: 0 1px 2px rgba(16, 24, 40, .04); }}
[data-testid="stMetric"] {{ background: #fff; box-shadow: 0 1px 2px rgba(16, 24, 40, .04); }}
.ss-status {{ display: flex; flex-direction: column; gap: 6px; font-size: .82rem; color: #374151; }}
.ss-status span::before {{ content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 50%;
                           margin-right: 8px; background: var(--c); }}
[data-testid="stMetricValue"] {{ font-weight: 800; }}
.ss-card {{ background: #fff; border: 1px solid {BORDER}; border-radius: 16px; padding: 18px 20px; }}
.ss-label {{ text-transform: uppercase; letter-spacing: .07em; font-size: .7rem; font-weight: 700; color: {MUTED}; }}
.ss-title {{ font-size: 1.05rem; font-weight: 700; color: {INK}; margin: 2px 0 10px; }}
.ss-hero {{ display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; }}
.ss-team {{ font-size: 1.55rem; font-weight: 800; color: {INK}; line-height: 1.15; }}
.ss-team.right {{ text-align: right; }}
.ss-dot {{ display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin: 0 8px 2px 0; }}
.ss-vs {{ font-weight: 700; color: {MUTED}; background: {SOFT}; border-radius: 999px; padding: 6px 14px; font-size: .85rem; }}
.ss-sub {{ color: {MUTED}; font-size: .82rem; margin-top: 4px; }}
.ss-chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }}
.ss-chip {{ display: inline-block; padding: 3px 10px; border-radius: 999px; background: {SOFT}; color: #374151;
            font-size: .75rem; font-weight: 600; border: 1px solid {BORDER}; }}
.ss-chip.warn {{ background: #fef3c7; color: #92400e; }}
.ss-chip.good {{ background: #d1fae5; color: #065f46; }}
.ss-rows {{ display: flex; flex-direction: column; }}
.ss-row {{ display: grid; grid-template-columns: 70px 1fr 70px; align-items: center; padding: 8px 0 7px;
           border-bottom: 1px solid #f1f2f4; }}
.ss-row:last-child {{ border-bottom: none; }}
.ss-val {{ justify-self: center; font-weight: 700; font-size: .9rem; color: {INK}; padding: 2px 10px; border-radius: 999px; }}
.ss-val.lead-us {{ background: {US}; color: #fff; }}
.ss-val.lead-them {{ background: {THEM}; color: #fff; }}
.ss-name {{ text-align: center; font-size: .84rem; color: #374151; }}
.ss-bar {{ grid-column: 1 / 4; display: flex; gap: 4px; height: 4px; margin-top: 7px; }}
.ss-bar span {{ display: block; height: 4px; border-radius: 4px; }}
.ss-legend {{ display: flex; justify-content: space-between; font-weight: 700; font-size: .85rem; margin-bottom: 4px; }}
.ss-finding {{ border: 1px solid {BORDER}; border-left: 4px solid var(--tone); border-radius: 12px; padding: 12px 14px;
               margin-bottom: 10px; background: #fff; }}
.ss-finding h4 {{ font-size: .95rem; font-weight: 700; margin: 0 0 4px; color: {INK}; }}
.ss-finding p {{ font-size: .85rem; color: #374151; margin: 0 0 6px; }}
.ss-finding .ss-do {{ font-size: .85rem; color: {INK}; }}
.ss-finding .ss-do b {{ color: var(--tone); }}
.ss-finding .ss-note {{ margin-top: 8px; font-size: .8rem; font-weight: 600; color: var(--note); }}
.ss-empty {{ text-align: center; padding: 28px 12px; color: {MUTED}; font-size: .9rem; }}
.ss-step {{ display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px;
            border-radius: 50%; background: {US}; color: #fff; font-weight: 700; font-size: .85rem; margin-right: 8px; }}
</style>
"""


def apply():
    """Load the app's styles (once per page run)."""
    st.session_state["_cards"] = 0
    st.html(CSS)


def card():
    """A white rounded card (a bordered container with a stable key the CSS can find)."""
    st.session_state["_cards"] = st.session_state.get("_cards", 0) + 1
    return st.container(border=True, key=f"card_{st.session_state['_cards']}")


def status(lines):
    """Small status lines with a colored dot: [(text, color)]."""
    st.html('<div class="ss-status">' + "".join(f'<span style="--c:{c}">{esc(t)}</span>' for t, c in lines)
            + "</div>")


def esc(text):
    return html.escape(str(text))


def label(text):
    st.html(f'<div class="ss-label">{esc(text)}</div>')


def hero(us, them, chips=(), us_sub="", them_sub=""):
    """The matchup banner at the top of a page."""
    chip_html = "".join(f'<span class="ss-chip {tone}">{esc(text)}</span>' for text, tone in chips)
    st.html(f"""
    <div class="ss-card">
      <div class="ss-hero">
        <div><div class="ss-label">Your team</div>
             <div class="ss-team"><span class="ss-dot" style="background:{US}"></span>{esc(us)}</div>
             <div class="ss-sub">{esc(us_sub)}</div></div>
        <div class="ss-vs">VS</div>
        <div style="text-align:right"><div class="ss-label">Opponent</div>
             <div class="ss-team right">{esc(them)}<span class="ss-dot" style="background:{THEM};margin:0 0 2px 8px"></span></div>
             <div class="ss-sub">{esc(them_sub)}</div></div>
      </div>
      <div class="ss-chips">{chip_html}</div>
    </div>""")


def compare_rows(us_name, them_name, rows):
    """FotMob-style comparison: value | label | value, leader highlighted, split bar below.

    rows: (label, our value, their value, text format, True if higher is better / None if neutral).
    """
    out = [f'<div class="ss-legend"><span style="color:{US}">{esc(us_name)}</span>'
           f'<span style="color:{THEM}">{esc(them_name)}</span></div><div class="ss-rows">']
    for name, a, b, fmt, higher_better in rows:
        lead_a = higher_better is not None and ((a > b) if higher_better else (a < b))
        lead_b = higher_better is not None and ((b > a) if higher_better else (b < a))
        total = (a + b) or 1
        out.append(f"""
        <div class="ss-row">
          <span class="ss-val {'lead-us' if lead_a else ''}">{fmt.format(a)}</span>
          <span class="ss-name">{esc(name)}</span>
          <span class="ss-val {'lead-them' if lead_b else ''}">{fmt.format(b)}</span>
          <div class="ss-bar"><span style="flex:{a / total:.3f};background:{US}"></span>
                              <span style="flex:{b / total:.3f};background:{THEM}"></span></div>
        </div>""")
    st.html("".join(out) + "</div>")


def finding_card(f, tone, action_label, note="", note_color=None):
    """One strength or weakness, with what to do about it (and an optional note)."""
    note_html = f'<div class="ss-note" style="--note:{note_color or tone}">{esc(note)}</div>' if note else ""
    st.html(f"""
    <div class="ss-finding" style="--tone:{tone}">
      <h4>{esc(f['title'])}</h4>
      <p>{esc(f['detail'])} <span class="ss-chip">{esc(f['evidence'])}</span></p>
      <div class="ss-do"><b>{esc(action_label)}:</b> {esc(f['action'])}</div>{note_html}
    </div>""")


def empty(message):
    st.html(f'<div class="ss-empty">{esc(message)}</div>')


def step(number, title):
    st.html(f'<div style="display:flex;align-items:center;margin:6px 0 4px">'
            f'<span class="ss-step">{number}</span><span class="ss-title" style="margin:0">{esc(title)}</span></div>')
