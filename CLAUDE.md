# Sportive Scout: Project Guide for Claude Code

## What this is
A personal soccer film analysis tool. The user (a high school student) wants to analyze
his own team's game film and an opponent's film, then get a scouting report and a
matchup game plan: formations, tendencies, strengths, weaknesses, standout players,
and heat maps. Until the user has their own team's film, testing uses pro or other
openly licensed matches. Pick two teams, one video of each.

The goal is depth coaches can't get from just watching film: ball heat maps (overall,
in possession, out of possession), formation in and out of possession (dots with
position labels, no player numbers needed), shot maps, which positions scored the goals,
then strengths/weaknesses for both teams and how to counter each strength and exploit
each weakness. Every pattern keeps the moments behind it so it can be checked on film.

Later this code will become a paid web app for coaches (Next.js on Vercel + a Python
worker using the Claude API). So keep the code clean and modular, and keep the
"analysis" step separate from everything else so it can be swapped out.

The user is learning. After each stage, explain in plain language what you built,
how to run it, and what to check. Avoid unexplained jargon.

## Two ways to do the analysis step
Everything after the analysis step (stats, insights, reports, app) works the same
whichever one wrote the logs.

**A. Claude Code logs by hand (no API key, uses the Claude Pro plan).**
- Do NOT call the Anthropic API or ask for an API key in this mode.
- YOU (Claude Code) look at the grid images directly and write the logs
  (`ManualClaudeCodeAnalyzer` in `src/analyzer.py`).
- Pro has usage limits, so be efficient: work batch by batch and save after every batch
  so work can stop and resume.
- To go faster, run several agents at once: each one runs `claim` (below) so it gets
  its own batch. Saving is locked, so parallel saves never lose entries.

**B. Automatic with the Claude API (needs `ANTHROPIC_API_KEY`, set by the user in `.env`).**
- `ApiAnalyzer` in `src/api_analyzer.py` sends grids to Claude (default Claude Opus 5.5,
  structured JSON output that matches the log format) and `src/batch_runner.py` runs many
  small chunks at the same time, caching every answer in `frames/<game>/pass<N>/analysis/`.
- `python -m src.run --game GAME_ID` (or the app's Analyze film page) does the whole game.
- Never paste or print the key; it lives only in `.env` (git-ignored) or the environment.

## Folder structure
```
Sportive-Scout/
  CLAUDE.md, README.md, requirements.txt, requirements-dev.txt, pytest.ini
  app.py                # Streamlit app entry (streamlit run app.py)
  games.yaml            # matchup + info about each game (the app can fill it in)
  film/                 # raw videos (git-ignored)
  frames/               # extracted frames, grids, API answers, clips (git-ignored)
  logs/                 # JSON moment logs + progress files
  reports/              # markdown + HTML reports + PNGs
  sample/               # FAKE demo games (games.yaml committed; logs/reports generated)
  src/
    config.py           # loads/validates games.yaml, video time <-> half / game minute
    extract.py          # Pass 1 (every 4s) + Pass 2 (every 1s around goals/shots), parallel ffmpeg
    analyzer.py         # analysis interface, safe saving, claim (parallel agents)
    api_analyzer.py     # Claude API analyzer (prompt, schema, cost)
    batch_runner.py     # many analysis requests at once, cache + resume
    run.py              # whole pipeline in one command
    aggregate.py        # logs -> team stats ("profiles")
    insights.py         # strengths and weaknesses as plain stats, matchup pairing
    visualize.py        # PNG field drawings and charts for reports
    report.py           # markdown + printable HTML reports
    media.py            # frame lookup, clips, previews for the app
    jobs.py             # background analysis jobs for the app
    sample_data.py      # generates the fake demo logs
    ui/                 # the app: theme.py (look), charts.py (interactive charts), pages/
  tests/                # pytest; fake_api.py stands in for the Claude API
  website/              # landing page + in-browser demo, published to GitHub Pages
```

## Website and browser demo
https://euryalus-kay.github.io/Sportive-Scout/ is built from `website/` by
`python website/build.py` and published to the `gh-pages` branch by
`.github/workflows/pages.yml` on every push to `main`. The demo is this app running in the
browser on stlite (Streamlit on Pyodide), packed from `app.py`, `src/` and `sample/`.
In the browser `config.IN_BROWSER` is True: there is no ffmpeg, no threads and no API, so
the app shows the demo data only. Keep imports at the top of modules browser-safe (import
`anthropic` and other heavy or native packages inside functions), and check the demo still
loads after big UI changes.

## games.yaml
`matchup: {our_team, opponent}` = the game being prepared for. Then one entry per video:
`id`, `file`, `team_analyzed` (us/opponent), `analyzed_team_name`, `other_team_name`,
`kit_colors`, `attacking_direction` (screen side in the 1st half), `kickoff_time`,
`first_half_end`, `second_half_start` (video times), `final_score`,
`goal_times` (list of `{time, team, position, how}`), `playoff`,
`opponent_strength` (weaker/similar/stronger), `notes`.
`python -m src.run` and the app check it with `config.validate_config` first.

## How to log a batch (mode A)
1. `python -m src.analyzer claim --game GAME_ID [--pass 2] [--agent NAME]` hands you the
   next batch nobody is logging, and lists the grids, cell timestamps, kit colors and
   attacking direction per half. (`next` shows the same without claiming.)
2. Look at each grid image. Each cell is labeled `video time | half game-minute`.
3. Write a JSON list (one entry per frame) to a scratch file, in SCREEN coordinates.
   The code flips to team-relative coordinates itself. Format is in the
   `src/analyzer.py` docstring: `timestamp`, `view` (wide/close/replay/other),
   `possession`, `ball_screen` [col 1-6 left->right along the pitch, row 1-4 far
   touchline -> near touchline], optional `ball_xy_screen` [0-100, 0-100], shapes + blocks,
   `events`, `players`, `confidence`, `note`.
   - Log each event ONCE, on the frame where it happens.
   - Shots: `{"type": "shot", "team", "outcome": goal|on_target|off_target|blocked,
     "position", "build_up": wide|central|counter|set_piece|long_ball|press}`.
   - Turnovers: `team` = the team that LOST the ball.
   - Set pieces: `{"type": "set_piece", "subtype": corner|free_kick|throw_in|penalty}`.
4. `python -m src.analyzer save --game GAME_ID --batch N --input FILE [--pass 2]`
   (this also releases the claim).
5. After Pass 1, run `python -m src.extract --game GAME_ID --pass 2` and log the key moments.
   Re-extracting a pass that has logs needs `--force` and clears that pass's logs.

## Build status
All stages built (extraction, logging, stats, insights, reports, interface), plus the
Claude API analyzer, parallel extraction and analysis, the one-command pipeline, the
multi-page app, a pytest suite (`python -m pytest`, run by GitHub Actions) and the website.
Tested on two full real games (Oct 2026, results in the README): fast and about $7 a game,
but one wide camera gives no readable formations and many "contested" frames.
Next: test film from a tactical camera, and consider an "unknown" possession option.

## Insights, not advice
The app shows insights only: a number, a short plain line and what it is based on
(e.g. "59%" / "of final-third possession down the left" / "209 frames"). It does not tell
the coach what to do. Keep new wording short, factual and free of filler.

## Ground rules
- Never invent things that can't be seen. If unsure, say so and lower confidence.
- Keep functions small and commented so the code is easy to reuse later.
- Run `python -m pytest` before committing; commit after each working stage with a clear message.
