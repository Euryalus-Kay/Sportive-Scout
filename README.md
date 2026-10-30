# Sportive Scout

Soccer film analysis: give it your team's game and your opponent's game, and get heat
maps, formations, shot maps, and the numbers that stand out for both teams, side by side.
Every insight lists the moments behind it, so you can check it on film.

**Website and live demo: https://euryalus-kay.github.io/Sportive-Scout/** (the demo is the
real app running in your browser with made-up teams, nothing to install).

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
| Overview | The matchup at a glance: key numbers side by side, head to head, what stands out, momentum, every goal |
| Your team / Opponent | Possession, shots, goals, momentum, heat maps, interactive shot maps, shapes, strengths and weaknesses |
| Matchup | Their numbers next to ours on the same thing, usual setups, set pieces, printable report |
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

**Cost:** the app shows an estimate before it starts. For one full game it's about $7 with
Claude Opus 5.5 (the default, most accurate), about $3.50 with Sonnet 5.5 and about 20 cents
with Haiku 5.5. The real spend is measured per batch and shown on the Analyze film page.

### Tested on real film
Two full high school games from a public-access cable broadcast (about 85 minutes of play
each, one wide camera, 1080p) ran through `python -m src.run --all` in October 2026.

| | Game 1 | Game 2 | Both |
|---|---|---|---|
| Frames read, one every 4 s | 1,265 | 1,296 | 2,561 |
| Frames read around goals and shots | 109 | 91 | 200 |
| Requests to Claude | 94 | 94 | 188 |
| Cost with Claude Opus 5.5 | $6.83 | $7.51 | $14.35 |
| Goals spotted in the first pass alone | 1 of 3 | 2 of 3 | 3 of 6 |
| Goals placed after the second pass | 3 of 3 | 3 of 3 | 6 of 6, all within 5 s, right team |

- **Time:** about 25 seconds per game to pull the frames, then 9 minutes 16 seconds to read
  both games with eight requests at a time. Every request finished, nothing had to be redone.
- **Still hard on this kind of film:** from one wide camera the players are small, so no
  frame gave a readable formation. About half the frames were marked contested and the
  average confidence was 0.43. The goals in Pass 2 came from the goal times entered for each
  game; Pass 1 on its own caught half of them. Film from a tactical camera is the next test.
- Test film from DoubleACS (Attleboro Access Cable System), CC BY-NC-ND 3.0, used for private
  testing only. It is not in this repo, and neither are its logs or reports.

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
| Insights | `src/insights.py` | Strengths and weaknesses as plain stats, and how the two teams line up |
| Visuals | `src/visualize.py` | Field drawings and charts for reports (PNG) |
| Reports | `src/report.py` | Markdown reports, PNGs and a printable HTML report in `reports/` |
| Interface | `app.py`, `src/ui/` | The Streamlit app; `src/ui/theme.py` holds the look (clean, Polymarket-style), `src/ui/charts.py` the interactive charts |
| Website | `website/` | The landing page and the in-browser demo (the app on [stlite](https://github.com/whitphx/stlite)). `python website/build.py` builds it into `_site/`; GitHub Actions publishes it to GitHub Pages on every push to `main` |

## Tests
```bash
pip install -r requirements-dev.txt
python -m pytest
```
The tests use a small generated video and a stand-in for the Claude API, so they need
ffmpeg but no API key. GitHub runs them on every push.
