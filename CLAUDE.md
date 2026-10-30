# Soccer Scout — Project Guide for Claude Code

## What this is
A personal soccer film analysis tool. The user (a high school student) wants to analyze
his own team's game film and an opponent's film, then get a scouting report and a
matchup game plan: formations, tendencies, strengths, weaknesses, standout players,
and heat maps.

Later this code will become a paid web app for coaches (Next.js on Vercel + a Python
worker using the Claude API). So keep the code clean and modular, and keep the
"analysis" step separate from everything else so it can be swapped out later.

The user is learning. After each stage, explain in plain language what you built,
how to run it, and what to check. Avoid unexplained jargon.

## Important constraint: no API calls in this version
This personal version runs on the user's Claude Pro plan through Claude Code.
- Do NOT call the Anthropic API or ask for an API key.
- YOU (Claude Code) look at the frame images directly and write the logs.
- Still, put the analysis logic behind a clear interface (e.g. `analyzer.py` with a
  `ManualClaudeCodeAnalyzer` now) so an `ApiAnalyzer` (Haiku / Sonnet) can be added later.

Because Pro has usage limits, be efficient: small images, frames combined into grids,
work in batches, save progress after every batch so work can stop and resume.

## Folder structure
```
soccer-scout/
  CLAUDE.md
  README.md
  requirements.txt
  games.yaml            # info about each game (user fills this in)
  film/                 # raw videos (git-ignored)
  frames/               # extracted frames and grids (git-ignored)
  logs/                 # JSON moment logs + progress files
  reports/              # markdown reports + heat map PNGs
  src/
    extract.py          # ffmpeg frame extraction + grid building
    analyzer.py         # analysis interface
    aggregate.py        # turns logs into stats
    visualize.py        # heat maps and charts (matplotlib)
    report.py           # report + game plan helpers
```
`.gitignore` must include: `film/`, `frames/`, `.env`, `__pycache__/`, `.venv/`.

## games.yaml (create a template the user fills in)
For each video:
- `file`: video filename in film/
- `team_analyzed`: "us" or "opponent"
- `our_team_name`, `opponent_name`
- `kit_colors`: team being analyzed vs. the other team (needed to tell teams apart)
- `attacking_direction`: which side of the screen (left/right) the analyzed team
  attacks in the 1st half
- `final_score`, `goal_times`, `playoff` (true/false)
- `notes`: lineup info, known players and jersey numbers, anything else

## Stages — build ONE stage at a time, then stop and let the user test

### Stage 1: Setup + frame extraction
- Check that Python and ffmpeg are installed; help install if not.
- Create the folder structure, requirements.txt, .gitignore, games.yaml template.
- `extract.py`: extract 1 frame every 4 seconds, resized to 768px wide.
- Combine every 4 consecutive frames into one 2x2 grid image, each cell labeled
  with its game timestamp (mm:ss).
- Group grids into numbered batches of 25.
- Add a `--minutes N` option to only process the first N minutes (for testing).
- Test on the first 5 minutes of one video.

### Stage 2: Moment logging (you look at the grids)
For each grid, write one JSON entry per frame to `logs/<game>.json`:
- `timestamp`
- `possession`: "analyzed_team" | "other_team" | "contested" | "dead_ball"
- `ball_zone`: on a 6x4 grid (6 zones along the length, 4 across the width),
  stored relative to the analyzed team's attacking direction (zone 6 = their attacking end).
  Use attacking_direction from games.yaml and flip it at halftime.
- `analyzed_team_shape` and `other_team_shape` (e.g. "4-4-2 low block", "high press")
- `events`: list of shot, goal, turnover, set_piece, cross, press, long_ball, etc.
- `players`: any readable jersey numbers involved
- `confidence`: 0-1 (be honest; wide footage makes some things unclear)
- `note`: short description of anything tactically interesting

Save `logs/<game>_progress.json` after every batch so the user can stop and resume.
Do a test on 5 minutes first and let the user compare against the film.

### Stage 3: Stats + visualizations
- `aggregate.py`: possession %, events by zone, turnovers by zone, shots by zone,
  shape frequencies, most-involved jersey numbers.
- `visualize.py`: ball-location heat map on a drawn soccer field (6x4 grid),
  turnover map, shot map, possession chart. Save PNGs to reports/.

### Stage 4: Reports
For each team, write `reports/<team>_report.md`:
- Likely formation(s) and how shape changes in and out of possession
- Attacking patterns (which side, build-up style, how chances are created)
- Defensive patterns and weaknesses (where they lose the ball, where they concede)
- Set pieces
- Standout players (by jersey number when readable)
- Label every tendency: **strong pattern** (5+ times), **possible pattern** (2-4),
  or **seen once**, with timestamps as evidence
- Account for game context: score, playoff stakes, quality of opponent

Then write `reports/game_plan.md` comparing the two teams:
- Opponent weaknesses we can exploit, matched to our strengths
- Opponent strengths we must watch out for, matched to our weaknesses
- Set piece notes and key things to check in the first 10-15 minutes of the game
- Embed the heat maps

### Stage 5: Simple local interface (optional)
A Streamlit page to choose games, edit context, run stages, and view reports
and heat maps. Keep it simple.

## Ground rules
- Never invent things that can't be seen. If unsure, say so and lower confidence.
- Keep functions small and commented so the code is easy to reuse later.
- Commit to git after each working stage with a clear message.
