# Sportive Scout — Project Guide for Claude Code

## What this is
A personal soccer film analysis tool. The user (a high school student) wants to analyze
his own team's game film and an opponent's film, then get a scouting report and a
matchup game plan: formations, tendencies, strengths, weaknesses, standout players,
and heat maps. Until the user has their own team's film, testing uses pro matches
(Champions League, World Cup) — pick two teams, one video of each.

The goal is depth coaches can't get from just watching film: ball heat maps (overall,
in possession, out of possession), formation in and out of possession (dots with
position labels, no player numbers needed), shot maps, which positions scored the goals,
then strengths/weaknesses for both teams and how to counter each strength and exploit
each weakness.

Later this code will become a paid web app for coaches (Next.js on Vercel + a Python
worker using the Claude API). So keep the code clean and modular, and keep the
"analysis" step separate from everything else so it can be swapped out later.

The user is learning. After each stage, explain in plain language what you built,
how to run it, and what to check. Avoid unexplained jargon.

## Important constraint: no API calls in this version
This personal version runs on the user's Claude Pro plan through Claude Code.
- Do NOT call the Anthropic API or ask for an API key.
- YOU (Claude Code) look at the frame images directly and write the logs.
- The analysis logic sits behind `Analyzer` in `src/analyzer.py`
  (`ManualClaudeCodeAnalyzer` now) so an `ApiAnalyzer` (Haiku / Sonnet) can be added later.

Because Pro has usage limits, be efficient: small images, frames combined into grids,
work in batches, save progress after every batch so work can stop and resume.

## Folder structure
```
Sportive-Scout/
  CLAUDE.md, README.md, requirements.txt
  app.py                # Streamlit interface (streamlit run app.py)
  games.yaml            # matchup + info about each game (user fills this in)
  film/                 # raw videos (git-ignored)
  frames/               # extracted frames and grids (git-ignored)
  logs/                 # JSON moment logs + progress files
  reports/              # markdown reports + PNGs
  sample/               # FAKE demo games (games.yaml committed; logs/reports generated)
  src/
    config.py           # loads games.yaml, video time <-> half / game minute
    extract.py          # Pass 1 (every 4s) + Pass 2 (every 1s around goals/shots)
    analyzer.py         # analysis interface + log/progress files
    aggregate.py        # logs -> team stats ("profiles")
    visualize.py        # field drawings: formation, heat maps, shot maps, charts
    insights.py         # strengths, weaknesses, counters, game plan matching
    report.py           # markdown reports + PNGs
    sample_data.py      # generates the fake demo logs
```

## games.yaml
`matchup: {our_team, opponent}` = the game being prepared for. Then one entry per video:
`id`, `file`, `team_analyzed` (us/opponent), `analyzed_team_name`, `other_team_name`,
`kit_colors`, `attacking_direction` (screen side in the 1st half), `kickoff_time`,
`first_half_end`, `second_half_start` (video times), `final_score`,
`goal_times` (list of `{time, team, position, how}`), `playoff`,
`opponent_strength` (weaker/similar/stronger), `notes`.

## How to log a batch (the analysis step)
1. `python -m src.analyzer next --game GAME_ID [--pass 2]` — lists the grids, cell
   timestamps, kit colors and attacking direction per half.
2. Look at each grid image. Each cell is labeled `video time | half game-minute`.
3. Write a JSON list (one entry per frame) to a scratch file, in SCREEN coordinates —
   the code flips to team-relative coordinates itself. Format is in the
   `src/analyzer.py` docstring: `timestamp`, `view` (wide/close/replay/other),
   `possession`, `ball_screen` [col 1-6 left->right, row 1-4 top->bottom],
   optional `ball_xy_screen` [0-100, 0-100], shapes + blocks, `events`, `players`,
   `confidence`, `note`.
   - Log each event ONCE, on the frame where it happens.
   - Shots: `{"type": "shot", "team", "outcome": goal|on_target|off_target|blocked,
     "position", "build_up": wide|central|counter|set_piece|long_ball|press}`.
   - Turnovers: `team` = the team that LOST the ball.
   - Set pieces: `{"type": "set_piece", "subtype": corner|free_kick|throw_in|penalty}`.
4. `python -m src.analyzer save --game GAME_ID --batch N --input FILE [--pass 2]`.
5. After Pass 1, run `python -m src.extract --game GAME_ID --pass 2` and log the key moments.

## Build status
All stages built (extraction, logging, stats, insights, reports, interface).
Next: test on real pro film — 5-minute extraction + logging test, user compares to film.

## Ground rules
- Never invent things that can't be seen. If unsure, say so and lower confidence.
- Keep functions small and commented so the code is easy to reuse later.
- Commit to git after each working stage with a clear message.
