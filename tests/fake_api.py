"""A stand-in for the Claude API, so the analyzer can be tested without a key.

It plugs into the real Anthropic SDK as its HTTP transport: the SDK builds
and sends real requests, and this answers with a real streaming response.
Each answer logs every frame the request asked for, so the whole pipeline
(analyzer -> batch runner -> log -> stats) runs for real.
"""
import json
import re
import threading

import anthropic
import httpx2

STAMPS = re.compile(r"Log these \d+ frames, in this order: (.+)\.$")


def frame_for(timestamp, shot=False):
    """A plausible answer for one frame."""
    return {
        "timestamp": timestamp, "view": "wide", "possession": "analyzed_team",
        "ball_screen": {"col": 5, "row": 2}, "ball_xy_screen": None,
        "analyzed_team_shape": "4-3-3", "analyzed_team_block": None,
        "other_team_shape": "4-4-2", "other_team_block": "low",
        "events": [{"type": "shot", "team": "analyzed_team", "outcome": "on_target",
                    "position": "ST", "build_up": "wide", "subtype": None,
                    "xy_screen": {"x": 88.0, "y": 45.0}}] if shot else [],
        "players": ["9"], "confidence": 0.8, "note": "",
    }


class FakeClaude:
    """Counts requests and answers them. `behaviors` can make some requests fail.

    behaviors: list of callables(request_json, call_number) -> httpx2.Response | None.
    Returning None means "answer normally".
    """

    def __init__(self, shots_every=0, behaviors=()):
        self.shots_every = shots_every
        self.behaviors = list(behaviors)
        self.requests = []
        self.headers = []
        self.lock = threading.Lock()

    def client(self):
        transport = httpx2.MockTransport(self.handle)
        return anthropic.Anthropic(api_key="test-key", base_url="https://api.test",
                                   max_retries=0, http_client=anthropic.DefaultHttpxClient(transport=transport))

    def handle(self, request):
        body = json.loads(request.content)
        with self.lock:
            self.requests.append(body)
            self.headers.append(dict(request.headers))
            call = len(self.requests)
        for behavior in self.behaviors:
            response = behavior(body, call)
            if response is not None:
                return response
        return stream_response(self.answer(body))

    def answer(self, body):
        text = body["messages"][0]["content"][-1]["text"]
        stamps = STAMPS.search(text).group(1).split(", ")
        frames = [frame_for(s, self.shots_every and i % self.shots_every == 0) for i, s in enumerate(stamps)]
        return json.dumps({"frames": frames})


def stream_response(text, stop_reason="end_turn", status=200):
    """A server-sent-events body like the real Messages API streams."""
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 9000, "output_tokens": 1,
                      "cache_read_input_tokens": 1700, "cache_creation_input_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "thinking", "thinking": "", "signature": ""}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("content_block_start", {"type": "content_block_start", "index": 1,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 1,
                                 "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                           "usage": {"output_tokens": 2000}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    body = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
    return httpx2.Response(status, headers={"content-type": "text/event-stream"}, content=body.encode())


def error_response(status, message="test error", kind="api_error"):
    return httpx2.Response(status, json={"type": "error", "error": {"type": kind, "message": message}})
