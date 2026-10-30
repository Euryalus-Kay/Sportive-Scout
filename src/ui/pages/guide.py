"""Guide: how the app works and how to read every chart, in plain language."""
import streamlit as st

from src.ui import theme

theme.label("Help")
st.markdown("<div class='ss-team'>How Sportive Scout works</div>", unsafe_allow_html=True)

with theme.card():
    theme.label("The idea")
    st.markdown(
        "Watching film tells you a lot, but it's hard to *count* things while you watch. Sportive Scout "
        "looks at a frame every 4 seconds of a game (and every second around shots and goals), writes "
        "down what it sees, and turns that into numbers, maps and a game plan you can check on film.")

c = st.columns(3, gap="medium")
steps = [("1. Add film", "Add your team's game and your opponent's game on **Analyze film**: the video, "
                         "the kits, the kickoff time and which way each team attacks."),
         ("2. Analyze", "With a Claude API key, press **Analyze**. Many parts of the video are read at the "
                        "same time, so a full game takes minutes. Without a key, Claude Code can do the "
                        "logging instead."),
         ("3. Scout", "Read **Overview**, the two team pages and the **Game plan**. Every pattern links "
                      "to the moments behind it, so you can check it on film.")]
for col, (title, text) in zip(c, steps):
    with col, theme.card():
        st.markdown(f"**{title}**")
        st.markdown(text)

with theme.card():
    theme.label("Reading the charts")
    st.markdown(
        "- **Every pitch is drawn with the team attacking left to right**, and their left touchline at the "
        "top, in both halves. So the right side of a heat map is always the end they attack.\n"
        "- **Heat maps** split the pitch into 24 zones and show the share of frames the ball was in each one. "
        "*With the ball* shows where a team builds attacks; *without the ball* shows where opponents get to.\n"
        "- **Shot maps**: a star is a goal, a filled dot is on target, a ring is off target or blocked. Colors "
        "show the shooter's position (forward, midfielder, defender). Click a shot to see it.\n"
        "- **Momentum**: each bar is 5 minutes. Above the line means that team had more of the ball.\n"
        "- **Formation** dots show the shape seen most often, pushed up or back by how high they defend "
        "(their *block*: low = deep near their own box, high = pressing near yours).\n"
        "- **Head to head** rows compare per-90-minute numbers from each team's own games. The highlighted "
        "number is better on that measure; style rows (presses, crosses) are not highlighted.")

with theme.card():
    theme.label("How sure is it?")
    st.markdown(
        "- Each pattern is labeled **strong pattern** (seen 5 or more times), **possible pattern** (2 to 4) "
        "or **seen once**. Treat \"seen once\" as something to watch for, not a fact.\n"
        "- **Confidence** (0 to 1) says how clearly the film could be read. Shaky phone video or a far-away "
        "camera gives lower confidence; below 0.5, read the numbers as rough.\n"
        "- Nothing is made up: when something can't be seen on film it is left empty, never guessed. Goals "
        "listed in the game's setup are always counted, even if a frame missed them.\n"
        "- The demo data (sidebar) is fake and only there so you can try the app.")
