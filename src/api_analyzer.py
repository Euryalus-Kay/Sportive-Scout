"""Automatic moment logging with the Claude API.

`ApiAnalyzer` has the same `analyze_batch` method as `ManualClaudeCodeAnalyzer`
(src/analyzer.py), so nothing else can tell which one wrote a log. For each
small batch of grids it sends the images to Claude together with the
logging rules below, and Claude answers with JSON that has to match a
schema (structured outputs): one entry per frame, in screen coordinates,
exactly like the hand-written logs.

The API key is read from the ANTHROPIC_API_KEY environment variable, or from
a .env file in the project folder (git-ignored): ANTHROPIC_API_KEY=sk-ant-...
Without a key, Claude Code can still log batches by hand (see CLAUDE.md).

Usage:
    python -m src.api_analyzer --check                 # is the key working?
    python -m src.api_analyzer --try GAME_ID           # analyze 2 grids and print them
To analyze whole games use src/run.py, which runs many requests at once.
"""
import argparse
import base64
import json
import math
import os
import threading
import time
from pathlib import Path

from src import config
from src.analyzer import AnalysisError, Analyzer, FatalAnalysisError, load_manifest

# Prices in dollars per million tokens (input, output, cache read).
MODELS = {
    "claude-opus-5-5": {"label": "Claude Opus 5.5 (most accurate)", "input": 4.00, "output": 20.00, "cache_read": 0.20},
    "claude-sonnet-5-5": {"label": "Claude Sonnet 5.5 (balanced)", "input": 2.00, "output": 10.00, "cache_read": 0.20},
    "claude-haiku-5-5": {"label": "Claude Haiku 5.5 (fastest, cheapest)", "input": 0.10, "output": 0.50, "cache_read": 0.01},
}
DEFAULT_MODEL = "claude-opus-5-5"
EFFORTS = ("low", "medium", "high")
DEFAULT_EFFORT = "medium"
MAX_TOKENS = 32000          # room for thinking plus ~32 frames of JSON
RETRIES = 2                 # extra tries for a bad answer (the SDK retries network errors itself)
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Sizes for the cost estimate, measured on two full games (Oct 2026): about 1,770 input
# tokens per grid, 3,740 cached prompt tokens per request and 155-175 output tokens per frame.
# Real usage is still measured while running.
TOKENS_PER_GRID = 1800      # a 1536x864 grid image is about width*height/750 tokens
PROMPT_TOKENS = 3700        # rules + game info, read from the prompt cache after the first request
OUTPUT_TOKENS_PER_FRAME = 170


# ---------- what Claude is told ----------

SYSTEM_PROMPT = """You log soccer game film for a scouting tool used by a high school team. Each image is a 2x2 grid of still frames from one game video. Each cell has a yellow label in its top-left corner: "video time | half game-minute", for example "12:34 | 1H 10'". The message says which frames each grid holds, in reading order: top-left, top-right, bottom-left, bottom-right.

Describe only what can be seen in each still frame. Never guess or invent. When something is not visible or you are unsure, use null (or an empty list) and lower the confidence.

TEAMS
- "analyzed_team" is the team being scouted; "other_team" is their opponent in this video. The message gives both kit colors and the side of the SCREEN the analyzed team attacks in each half.

PITCH POSITIONS (screen orientation; the software converts them to each team's view later)
- Picture the WHOLE pitch as the camera sees it. Columns run along its length: col 1 is the end with the goal on the LEFT of the screen, col 6 the end with the goal on the RIGHT (each column is one sixth of the pitch, the halfway line is between col 3 and col 4). Rows run across its width: row 1 is the FAR touchline (top of the screen), row 4 the NEAR touchline (the camera side).
- Use the pitch markings (halfway line, center circle, penalty boxes, touchlines, goals) to place the ball on the whole pitch, even when the camera shows only part of it.
- ball_screen: {"col", "row"} of the ball, or null if the ball can't be seen or placed.
- ball_xy_screen: {"x", "y"} from 0 to 100 (x: 0 = left goal line, 100 = right goal line; y: 0 = far touchline, 100 = near touchline). Give it when you can place the ball fairly precisely, always for shots; otherwise null.

PER FRAME
- view: "wide" (game view showing a good part of the pitch), "close" (close-up of players, coach or crowd), "replay" (slow motion or a replay), "other" (graphics, adverts, halftime, no game).
- possession: "analyzed_team" or "other_team" (who controls the ball), "contested" (loose ball, header, 50-50), "dead_ball" (ball out of play, foul, stoppage, celebration).
- analyzed_team_shape / other_team_shape: outfield formation from back to front, digits that add up to 10, like "4-4-2", "4-3-3", "4-2-3-1", "3-5-2". Only when most of that team's outfield players are visible and their lines are clear; otherwise null.
- analyzed_team_block / other_team_block: how high that team defends when it does NOT have the ball: "low" (deep, near its own box), "mid" (around the middle third), "high" (pressing in the opponent's half). null when that team has the ball or you can't tell.
- players: jersey numbers you can clearly read on players near the ball, as strings. Never guess a number.
- confidence: 0 to 1 for the whole entry (about 0.8 for a clear wide view, 0.5 when partly unclear, below 0.4 when very hard to read).
- note: a few words that help a coach, or "".

EVENTS (log each event once, on the frame where it happens, never again on later frames that show the aftermath; most frames have no events)
- shot: a player strikes at goal. team = shooting team. outcome: "goal", "on_target" (saved, or going in), "off_target" or "blocked". position: the shooter's role if you can tell (GK, CB, LB, RB, LWB, RWB, DM, CM, AM, LM, RM, LW, RW, ST, CF), else null. build_up: how the chance was made, "wide", "central", "counter", "set_piece", "long_ball" or "press", else null. xy_screen: where the shot was taken from. A goal is a shot with outcome "goal".
- turnover: the ball is lost (pass intercepted, tackled, dispossessed). team = the team that LOST the ball.
- press: two or more players close down the ball carrier to win it back. team = the pressing team.
- cross: a ball delivered from a wide area into the box. team = the crossing team.
- long_ball: a long forward pass of about 30 m or more that skips midfield. team = the passing team.
- counter: a fast attack right after winning the ball, against a defense that is out of shape. team = the attacking team.
- set_piece: subtype "corner", "free_kick", "throw_in", "penalty" or "goal_kick" being taken. team = the team taking it.
Use null for fields that don't apply to an event type.

Return one entry per frame, in the order listed in the message, copying each timestamp exactly (mm:ss)."""

PASS2_NOTE = ("These frames are one second apart around a key moment (a goal or a shot). Read them as a "
              "sequence: log the shot once, on the frame where the ball is struck (or the closest frame), "
              "with its outcome, the shooter's position, the build-up and xy_screen. If it ends in a goal, "
              "the outcome is goal.")


def _nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def _enum(values):
    return {"type": "string", "enum": list(values)}


def _point(*names):
    return {"type": "object", "properties": {n: {"type": "number"} for n in names},
            "required": list(names), "additionalProperties": False}


EVENT_SCHEMA = {
    "type": "object",
    "properties": {
        "type": _enum(["shot", "turnover", "press", "cross", "long_ball", "counter", "set_piece"]),
        "team": _enum(["analyzed_team", "other_team"]),
        "outcome": _nullable(_enum(["goal", "on_target", "off_target", "blocked"])),
        "position": _nullable(_enum(["GK", "CB", "LB", "RB", "LWB", "RWB", "DM", "CM", "AM",
                                     "LM", "RM", "LW", "RW", "ST", "CF"])),
        "build_up": _nullable(_enum(["wide", "central", "counter", "set_piece", "long_ball", "press"])),
        "subtype": _nullable(_enum(["corner", "free_kick", "throw_in", "penalty", "goal_kick"])),
        "xy_screen": _nullable(_point("x", "y")),
    },
    "required": ["type", "team", "outcome", "position", "build_up", "subtype", "xy_screen"],
    "additionalProperties": False,
}

FRAME_SCHEMA = {
    "type": "object",
    "properties": {
        "timestamp": {"type": "string"},
        "view": _enum(["wide", "close", "replay", "other"]),
        "possession": _enum(["analyzed_team", "other_team", "contested", "dead_ball"]),
        "ball_screen": _nullable({"type": "object",
                                  "properties": {"col": {"type": "integer"}, "row": {"type": "integer"}},
                                  "required": ["col", "row"], "additionalProperties": False}),
        "ball_xy_screen": _nullable(_point("x", "y")),
        "analyzed_team_shape": _nullable({"type": "string"}),
        "analyzed_team_block": _nullable(_enum(["low", "mid", "high"])),
        "other_team_shape": _nullable({"type": "string"}),
        "other_team_block": _nullable(_enum(["low", "mid", "high"])),
        "events": {"type": "array", "items": EVENT_SCHEMA},
        "players": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "note": {"type": "string"},
    },
    "required": ["timestamp", "view", "possession", "ball_screen", "ball_xy_screen",
                 "analyzed_team_shape", "analyzed_team_block", "other_team_shape",
                 "other_team_block", "events", "players", "confidence", "note"],
    "additionalProperties": False,
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"frames": {"type": "array", "items": FRAME_SCHEMA}},
    "required": ["frames"],
    "additionalProperties": False,
}


def game_context(game):
    """The part of the message that is the same for every batch of one game."""
    kits = game["kit_colors"]
    first, second = config.attacking_direction(game, 1), config.attacking_direction(game, 2)
    return (f"Game: {game.get('analyzed_team_name')} (analyzed_team) vs "
            f"{game.get('other_team_name')} (other_team).\n"
            f"Kits: analyzed_team wears {kits.get('analyzed_team') or 'unknown colors'}; "
            f"other_team wears {kits.get('other_team') or 'unknown colors'}.\n"
            f"Screen direction: in the 1st half (labels 1H) the analyzed_team attacks toward the "
            f"{first.upper()} of the screen; in the 2nd half (labels 2H) it attacks toward the "
            f"{second.upper()}. Frames labeled 'break' are before kickoff or at halftime.")


def build_request(game, pass_no, batch, model=DEFAULT_MODEL, effort=DEFAULT_EFFORT):
    """The Messages API request for one batch (or chunk) of grids."""
    content = [{"type": "text", "text": game_context(game), "cache_control": {"type": "ephemeral"}}]
    if pass_no == 2:
        content.append({"type": "text", "text": PASS2_NOTE})
    stamps, n = [], len(batch["grids"])
    for i, grid in enumerate(batch["grids"], start=1):
        cells = "; ".join(f"{c['cell']} = {c['timestamp']} ({_half_text(c)})" for c in grid["cells"])
        content.append({"type": "text", "text": f"Grid {i} of {n}: {cells}."})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": _image_b64(grid["grid"])}})
        stamps += [c["timestamp"] for c in grid["cells"]]
    content.append({"type": "text", "text": f"Log these {len(stamps)} frames, in this order: "
                                            f"{', '.join(stamps)}."})
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": content}],
        "output_config": {"effort": effort,
                          "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}},
    }


def _half_text(cell):
    half = {0: "break", 1: "1st half", 2: "2nd half"}[cell["half"] or 0]
    return half if not cell["half"] else f"{half}, minute {int(cell['game_minute']) + 1}"


def _image_b64(rel_path):
    return base64.standard_b64encode(config.project_path(rel_path).read_bytes()).decode("ascii")


# ---------- reading the answer ----------

def parse_frames(message, cells):
    """Turn Claude's answer into raw entries for the given cells."""
    if message.stop_reason == "refusal":
        raise AnalysisError("Claude declined to analyze these frames.")
    text = "".join(block.text for block in message.content if block.type == "text").strip()
    try:
        frames = json.loads(text)["frames"]
    except (json.JSONDecodeError, KeyError, TypeError) as err:
        raise AnalysisError(f"the answer was not the expected JSON ({err.__class__.__name__})") from None
    wanted = {c["timestamp"] for c in cells}
    entries, seen = [], set()
    for frame in frames:
        raw = to_raw_entry(frame)
        if raw["timestamp"] in wanted and raw["timestamp"] not in seen:
            seen.add(raw["timestamp"])
            entries.append(raw)
    if len(entries) < 0.75 * len(wanted):
        raise AnalysisError(f"only {len(entries)} of {len(wanted)} frames came back")
    return entries


def to_raw_entry(frame):
    """One frame of the API answer -> the raw entry format analyzer.py stores."""
    raw = {
        "timestamp": _canonical_time(frame.get("timestamp", "")),
        "view": frame.get("view", "other"),
        "possession": frame.get("possession", "contested"),
        "analyzed_team_shape": frame.get("analyzed_team_shape"),
        "analyzed_team_block": frame.get("analyzed_team_block"),
        "other_team_shape": frame.get("other_team_shape"),
        "other_team_block": frame.get("other_team_block"),
        "events": [_event(e) for e in frame.get("events") or []],
        "players": [str(p).strip("# ") for p in frame.get("players") or [] if str(p).strip("# ")],
        "confidence": _clamp(frame.get("confidence", 0.5), 0.0, 1.0),
        "note": frame.get("note") or "",
    }
    ball = frame.get("ball_screen")
    if ball:
        raw["ball_screen"] = [int(_clamp(round(ball["col"]), 1, 6)), int(_clamp(round(ball["row"]), 1, 4))]
    xy = frame.get("ball_xy_screen")
    if xy:
        raw["ball_xy_screen"] = [_clamp(xy["x"], 0, 100), _clamp(xy["y"], 0, 100)]
    return raw


def _event(event):
    """Drop empty fields; points become [x, y] like hand-written logs."""
    out = {k: v for k, v in event.items() if v is not None and k != "xy_screen"}
    if event.get("xy_screen"):
        out["xy_screen"] = [_clamp(event["xy_screen"]["x"], 0, 100), _clamp(event["xy_screen"]["y"], 0, 100)]
    return out


def _canonical_time(value):
    """ "0:05", "00:05" and " 00:05 " all become "00:05"."""
    try:
        return config.format_time(config.parse_time(str(value).strip()))
    except (ValueError, TypeError):
        return str(value).strip()


def _clamp(value, lo, hi):
    return max(lo, min(hi, float(value)))


# ---------- cost ----------

def usage_of(message, model):
    """Token counts and dollar cost of one response."""
    u = message.usage
    usage = {"requests": 1,
             "input_tokens": u.input_tokens or 0,
             "output_tokens": u.output_tokens or 0,
             "cache_read_tokens": getattr(u, "cache_read_input_tokens", None) or 0,
             "cache_write_tokens": getattr(u, "cache_creation_input_tokens", None) or 0}
    usage["cost"] = cost_of(usage, model)
    return usage


def cost_of(usage, model):
    """Dollars for a usage dict (cache writes cost 1.25x input)."""
    price = MODELS.get(model, MODELS[DEFAULT_MODEL])
    return (usage["input_tokens"] * price["input"] + usage["output_tokens"] * price["output"]
            + usage["cache_read_tokens"] * price["cache_read"]
            + usage["cache_write_tokens"] * price["input"] * 1.25) / 1e6


def add_usage(total, usage):
    """Add one usage dict into another (in place) and return it."""
    for key, value in usage.items():
        total[key] = total.get(key, 0) + value
    return total


def estimate_cost(n_grids, model=DEFAULT_MODEL, grids_per_chunk=4):
    """Rough dollars to analyze n_grids grids. Real usage is shown while running."""
    chunks = math.ceil(n_grids / max(1, grids_per_chunk))
    usage = {"input_tokens": n_grids * TOKENS_PER_GRID + chunks * 200,
             "cache_read_tokens": chunks * PROMPT_TOKENS,
             "cache_write_tokens": PROMPT_TOKENS,
             "output_tokens": n_grids * 4 * OUTPUT_TOKENS_PER_FRAME}
    return cost_of(usage, model)


# ---------- the analyzer ----------

def api_key_available():
    """True when an API key (or other Claude credential) is set up."""
    config.load_env()
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or (Path.home() / ".config" / "anthropic").exists())


class ApiAnalyzer(Analyzer):
    """Logs frames by sending grids to the Claude API. Safe to share across threads."""

    def __init__(self, model=DEFAULT_MODEL, effort=DEFAULT_EFFORT, client=None, retries=RETRIES):
        self.model, self.effort, self.retries = model, effort, retries
        self._client = client
        self._client_lock = threading.Lock()

    @property
    def client(self):
        with self._client_lock:
            if self._client is None:
                import anthropic
                config.load_env()
                self._client = anthropic.Anthropic(max_retries=4, timeout=600)
            return self._client

    def analyze_batch(self, game, pass_no, batch):
        return self.analyze(game, pass_no, batch)[0]

    def analyze(self, game, pass_no, batch):
        """(raw entries, usage) for every frame of a small batch of grids."""
        cells = [c for g in batch["grids"] for c in g["cells"]]
        usage, last_error = {}, None
        for attempt in range(1 + self.retries):
            message = self._send(build_request(game, pass_no, batch, self.model, self.effort))
            if message is None:             # a temporary API problem, try again
                last_error = AnalysisError("the API was busy or could not be reached")
                time.sleep(5 * (attempt + 1))
                continue
            add_usage(usage, usage_of(message, self.model))
            if message.stop_reason == "max_tokens" and len(batch["grids"]) > 1:
                return self._split(game, pass_no, batch, usage)
            try:
                return parse_frames(message, cells), usage
            except AnalysisError as err:
                last_error = err
        raise AnalysisError(f"no usable answer after {1 + self.retries} tries"
                            + (f" ({last_error})" if last_error else ""))

    def _split(self, game, pass_no, batch, usage):
        """The answer was too long: analyze each half of the batch on its own."""
        half = len(batch["grids"]) // 2
        entries = []
        for grids in (batch["grids"][:half], batch["grids"][half:]):
            part, part_usage = self.analyze(game, pass_no, {**batch, "grids": grids})
            entries += part
            add_usage(usage, part_usage)
        return entries, usage

    def _send(self, params):
        """One streamed request. Returns the final message, or None on a temporary error."""
        import anthropic
        try:
            # fallbacks="default": if the model declines for policy reasons, the API
            # retries on its recommended fallback model instead of returning a refusal.
            with self.client.beta.messages.stream(**params, betas=[FALLBACK_BETA],
                                                  fallbacks="default") as stream:
                return stream.get_final_message()
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as err:
            raise FatalAnalysisError(f"the API key was rejected ({err.status_code}). "
                                     "Check ANTHROPIC_API_KEY.") from None
        except anthropic.NotFoundError:
            raise FatalAnalysisError(f"the model {self.model} is not available to this API key.") from None
        except anthropic.BadRequestError as err:
            raise FatalAnalysisError(f"the API rejected the request: {err.message}") from None
        except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError):
            return None


# ---------- command line ----------

def main():
    parser = argparse.ArgumentParser(description="Claude API analyzer: quick checks.")
    parser.add_argument("--check", action="store_true", help="check that the API key works")
    parser.add_argument("--try", dest="try_game", metavar="GAME_ID", help="analyze 2 grids of a game and print them")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODELS))
    parser.add_argument("--effort", default=DEFAULT_EFFORT, choices=EFFORTS)
    parser.add_argument("--config", default=str(config.GAMES_FILE))
    args = parser.parse_args()
    if not api_key_available():
        raise SystemExit("No API key found. Put ANTHROPIC_API_KEY=... in a .env file in the "
                         "project folder (it is git-ignored), or set it in your terminal.")
    analyzer = ApiAnalyzer(args.model, args.effort)
    if args.check:
        info = analyzer.client.models.retrieve(args.model)
        print(f"API key works. {info.display_name} ({info.id}) is available.")
    if args.try_game:
        game = config.get_game(config.load_config(args.config), args.try_game)
        batch = load_manifest(game["id"], 1)["batches"][0]
        entries, usage = analyzer.analyze(game, 1, {**batch, "grids": batch["grids"][:2]})
        print(json.dumps(entries, indent=1))
        print(f"{len(entries)} frames, {usage['input_tokens']} input + {usage['output_tokens']} "
              f"output tokens, ${usage['cost']:.3f}")


if __name__ == "__main__":
    main()
