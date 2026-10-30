"""Guide: how the app works and how to read every chart."""
import streamlit as st

from src.ui import theme

theme.page_title("Help", "How Sportive Scout works")
st.space("small")

c = st.columns(3, gap="medium")
steps = [("1 · Add film", "On Analyze film, add one game of your team and one of your opponent: the video, "
                         "kit colors, kickoff time and which way each team attacks."),
         ("2 · Analyze", "The app takes a frame every 4 seconds (every second around shots and goals) and "
                        "logs possession, ball position, shapes and events. With a Claude API key this runs "
                        "automatically; without one, Claude Code does the logging."),
         ("3 · Read", "Overview, the two team pages and Matchup show the numbers. Every insight lists the "
                      "moments behind it, so you can check it on film.")]
for col, (title, text) in zip(c, steps):
    with col, theme.card():
        theme.heading(title)
        st.markdown(text)

with theme.card():
    theme.heading("Reading the charts")
    st.markdown(
        "- Every pitch shows the team attacking **left to right**, with their left touchline at the top, in "
        "both halves. The right side of a heat map is always the end they attack.\n"
        "- **Heat maps** split the pitch into 24 zones and show the share of frames the ball was in each one.\n"
        "- **Shot maps**: star = goal, filled dot = on target, ring = off target or blocked. Color shows the "
        "shooter's position. Click a shot to see it.\n"
        "- **Momentum**: one bar per 5 minutes. Above the line means more of the ball.\n"
        "- **Shape** dots show the formation seen most often, moved up or back by the block "
        "(low = deep near their own box, high = pressing).\n"
        "- **Head to head** compares per-90 numbers from each team's own games. The colored number is better "
        "on that measure; style rows (presses, crosses, blocks) are not colored.")

with theme.card():
    theme.heading("How reliable it is")
    st.markdown(
        "- Each insight says what it is based on, and how often it was seen: **strong pattern** (5 or more), "
        "**possible pattern** (2 to 4) or **seen once**.\n"
        "- **Confidence** (0 to 1) is how clearly the film could be read. Below 0.5, treat the numbers as rough.\n"
        "- Nothing is filled in when it can't be seen. Goals entered in a game's setup always count, even if "
        "no frame caught them.\n"
        "- The demo data in the sidebar is made up.")
