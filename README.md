# Sportive Scout

Soccer film analysis: upload your team's game and your opponent's game, get heat maps,
formations, shot maps, strengths and weaknesses for both teams, and a game plan for
the matchup.

## Setup (once)
Needs Python 3 and ffmpeg (`brew install ffmpeg`).
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Try the app with fake demo data
```bash
streamlit run app.py
```
Or in VS Code: **Run and Debug → "Sportive Scout app"**. The app opens in your browser
in *Sample (fake demo)* mode. The teams in it are made up.

## Analyze real games
1. Put the two videos in `film/` (one of your team, one of your opponent).
2. Fill in `games.yaml` (team names, kit colors, attacking direction, kickoff and
   2nd-half start times, goal times).
3. Test extraction on 5 minutes:
   `python -m src.extract --game GAME_ID --minutes 5`
   then look at the grids in `frames/GAME_ID/pass1/`.
4. Ask Claude Code to log the batches (see "How to log a batch" in CLAUDE.md).
5. Extract key moments: `python -m src.extract --game GAME_ID --pass 2`, and log them.
6. Open the app and switch the sidebar to *My games*. Or write markdown reports with
   `python -m src.report`.

## How it works
| Step | File | What it does |
|---|---|---|
| Extract | `src/extract.py` | Pass 1: a frame every 4s in 2x2 grids. Pass 2: a frame every 1s around goals and shots |
| Analyze | `src/analyzer.py` | Turns what's seen in each frame into a log entry (Claude Code now, Claude API later) |
| Stats | `src/aggregate.py` | Possession, heat maps, shapes, shots, goals by position, turnovers |
| Insights | `src/insights.py` | Strengths, weaknesses, counters, and the game plan |
| Visuals | `src/visualize.py` | Field drawings and charts |
| Reports | `src/report.py` | Markdown reports + PNGs in `reports/` |
| Interface | `app.py` | Streamlit page with team tabs, game plan and progress |
