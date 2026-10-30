"""Analysis jobs that keep running while you use the rest of the app.

The app starts a job on a background thread and checks on it every couple
of seconds, so a long analysis never freezes the page, and you can look at
other pages (or close the tab) while it runs.
"""
import threading
import time
from dataclasses import dataclass, field

from src import config, extract, run
from src.analyzer import FatalAnalysisError


@dataclass
class Job:
    kind: str                       # "analyze" (extract + Claude API) or "extract" (frames only)
    game_ids: list
    opts: run.Options
    state: str = "running"          # running | done | stopped | failed
    game: str = ""                  # the game being worked on now
    stages: dict = field(default_factory=dict)      # latest progress update per stage
    notes: list = field(default_factory=list)       # failed chunks and other things to report
    error: str = ""
    cost: float = 0.0
    started: float = field(default_factory=time.time)
    finished: float = None
    stop: threading.Event = field(default_factory=threading.Event)

    def update(self, event):
        self.stages[event["stage"]] = {**event, "game": self.game}

    @property
    def running(self):
        return self.state == "running"

    @property
    def elapsed(self):
        return (self.finished or time.time()) - self.started


_LOCK = threading.Lock()
_CURRENT = {}


def current():
    """The most recent job (running or finished), or None."""
    with _LOCK:
        return _CURRENT.get("job")


def start(kind, game_ids, opts):
    """Start a job unless one is already running. Returns the job."""
    with _LOCK:
        job = _CURRENT.get("job")
        if job and job.running:
            return job
        job = Job(kind, list(game_ids), opts)
        _CURRENT["job"] = job
    threading.Thread(target=_run, args=(job,), daemon=True, name="scout-job").start()
    return job


def _run(job):
    try:
        cfg = config.load_config()
        for game_id in job.game_ids:
            game = config.get_game(cfg, game_id)
            job.game = game_id
            if job.kind == "extract":
                job.update({"stage": "extract1", "done": 0, "total": 1})
                extract.run_pass1(game, job.opts.minutes, job.opts.extract_workers,
                                  progress=lambda d, t: job.update({"stage": "extract1", "done": d, "total": t}))
                continue
            summary = run.analyze_game(game, job.opts, progress=job.update, stop=job.stop)
            job.cost += summary["cost"]
            job.notes += [f"{game_id}: {line}" for line in summary["failed"]]
            if summary["stopped"]:
                job.state = "stopped"
                break
        if job.kind == "analyze":
            run.build_reports(cfg)
        if job.state == "running":
            job.state = "done"
    except FatalAnalysisError as err:
        job.state, job.error = "failed", str(err)
    except Exception as err:        # shown in the app instead of crashing it
        job.state, job.error = "failed", f"{err.__class__.__name__}: {err}"
    finally:
        job.finished = time.time()
