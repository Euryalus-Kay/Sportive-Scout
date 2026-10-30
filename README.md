# Sportive Scout

Soccer film analysis: give it your team's game and your opponent's game, and get heat
maps, formations, shot maps, strengths and weaknesses for both teams, and a game plan for
the matchup. Every pattern links back to the moments behind it, so you can check it on film.

## Setup (once)
Needs Python 3.10 or newer and ffmpeg (`brew install ffmpeg`).
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Open the app
```bash
streamlit run app.py
```
Or in VS Code: **Run and Debug → "Sportive Scout app"**. It opens in your browser with
*demo data* (made-up teams) so you can try everything first. Switch the sidebar to
**My games** once your film is analyzed.

| Page | What it shows |
|---|---|
| Overview | The matchup at a glance: head-to-head numbers, the plan in short, momentum, every goal |
| Your team / Opponent | Possession, shots, goals, momentum, heat maps, interactive shot maps, shapes, strengths and weaknesses |
| Game plan | How to attack them, how to stop them, what to fix, set pieces, a first-15-minutes checklist, printable report |
| Moments | Every logged event in one list; click one to see the frame and a 12-second clip |
| Analyze film | Add the matchup and games, upload videos, find kickoff times, run the analysis with live progress |
| Guide | How to read every chart, in plain language |

## Analyze real games

### Automatic, with a Claude API key (fast)
1. Put your key in a file called `.env` in this folder (it is git-ignored):
   `ANTHROPIC_API_KEY=sk-ant-...` (or paste it on the **Analyze film** page).
2. On **Analyze film**: name the two teams, add one game for each (video, kit colors,
   kickoff time, which way they attack), then press **Analyze**. Try *Quick test (5 min)* first.

The same from the terminal:
```bash
python -m src.run --all --estimate          # what it would cost
python -m src.run --game GAME_ID --minutes 5  # quick 5-minute test
python -m src.run --all                     # every game, then the reports
```

**Why it's fast without losing quality:** the video is cut into pieces that several ffmpeg
processes decode at the same time, and the frames are sent to Claude in small chunks (16
frames each), many at once. Small chunks keep the quality up because the model studies fewer
images per request; running many at once keeps it fast. Every answer is saved the moment it
arrives, so stopping or crashing never loses paid work, and running again skips what's done.

**Cost:** the app shows an estimate before it starts. The built-in estimate for one full game
is about $9 with Claude Opus 5.5 (the default, most accurate), about $5 with Sonnet 5.5 and
well under $1 with Haiku 5.5. Treat those as rough until you've run a few games: the real
spend is measured per batch and shown on the Analyze film page.

### By hand, with Claude Code (no API key)
1. Put the videos in `film/` and fill in the games on the **Analyze film** page (or `games.yaml`).
2. Extract frames: `python -m src.extract --game GAME_ID` (try `--minutes 5` first).
3. Ask Claude Code to log the batches (see "How to log a batch" in CLAUDE.md). It can run
   several agents at once: each one claims a different batch, so they never collide.
4. Key moments: `python -m src.extract --game GAME_ID --pass 2`, then log those too.
5. Write reports: `python -m src.report` (also saves a printable `scouting_report.html`).

## How it works
| Step | File | What it does |
|---|---|---|
| Extract | `src/extract.py` | Pass 1: a frame every 4 s in 2x2 grids. Pass 2: a frame every second around goals and shots. Parallel ffmpeg, exact frame times |
| Analyze | `src/analyzer.py` | The analysis interface, safe saving, batch claiming for parallel Claude Code agents |
| | `src/api_analyzer.py` | Logs frames through the Claude API (structured JSON output) |
| | `src/batch_runner.py` | Runs many analysis requests at once, caches and resumes |
| Pipeline | `src/run.py` | One command: extract, analyze, key moments, reports |
| Stats | `src/aggregate.py` | Possession, heat maps, shapes, shots, goals by position, turnovers, timeline, per-90 rates |
| Insights | `src/insights.py` | Strengths, weaknesses, counters and the game plan |
| Visuals | `src/visualize.py` | Field drawings and charts for reports (PNG) |
| Reports | `src/report.py` | Markdown reports, PNGs and a printable HTML report in `reports/` |
| Interface | `app.py`, `src/ui/` | The Streamlit app; `src/ui/theme.py` holds the look, `src/ui/charts.py` the interactive charts |

## Tests
```bash
pip install -r requirements-dev.txt
python -m pytest
```
The tests use a small generated video and a stand-in for the Claude API, so they need
ffmpeg but no API key. GitHub runs them on every push.
