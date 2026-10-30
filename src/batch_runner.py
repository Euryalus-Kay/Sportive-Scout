"""Runs an analyzer over a whole pass, with many requests at the same time.

Each batch from extract.py (25 grids) is cut into small chunks (4 grids, so
16 frames, by default) and several chunks go to the analyzer at once on
separate threads. Small chunks keep the quality up, because the model looks
at fewer images per request, and running many at once keeps it fast.

Every finished chunk is written to frames/<game>/pass<N>/analysis/ straight
away, and a batch is saved to the log as soon as all its chunks are back.
A crash or a stop only loses the chunks that were in flight, and running
again skips everything already done.

Pass 2 key moments are kept whole when they fit in one request, because a
shot is easier to read as one sequence of frames.
"""
import json
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from src import config
from src.analyzer import AnalysisError, FatalAnalysisError, load_manifest, load_progress, save_entries

DEFAULT_WORKERS = 6         # requests at the same time
GRIDS_PER_CHUNK = 4         # Pass 1: 16 frames per request
MOMENT_MAX_GRIDS = 8        # Pass 2: up to 32 frames (one key moment) per request


@dataclass
class Chunk:
    """A few grids of one batch: one request to the analyzer."""
    batch: int
    index: int
    grids: list

    @property
    def name(self):
        return f"b{self.batch:03d}_c{self.index:02d}"

    @property
    def frames(self):
        return sum(len(g["cells"]) for g in self.grids)


@dataclass
class PassReport:
    """What happened while analyzing one pass."""
    pass_no: int
    total_chunks: int = 0
    cached_chunks: int = 0
    done_chunks: int = 0
    saved_batches: list = field(default_factory=list)
    failed: list = field(default_factory=list)       # (chunk name, reason)
    problems: list = field(default_factory=list)     # skipped entries, with reasons
    usage: dict = field(default_factory=dict)
    seconds: float = 0.0
    stopped: bool = False
    fatal: str = ""

    @property
    def cost(self):
        return self.usage.get("cost", 0.0)

    def snapshot(self, elapsed):
        """A progress update the command line and the app can show."""
        finished = self.cached_chunks + self.done_chunks
        left = self.total_chunks - finished - len(self.failed)
        rate = self.done_chunks / elapsed if elapsed > 0 and self.done_chunks else 0
        return {"stage": f"analyze{self.pass_no}", "done": finished, "total": self.total_chunks,
                "failed": len(self.failed), "cost": self.cost, "elapsed": elapsed,
                "eta": left / rate if rate else None}


def plan_chunks(batch, pass_no, grids_per_chunk=GRIDS_PER_CHUNK):
    """Cut one batch into chunks of about the same size."""
    grids = batch["grids"]
    size = grids_per_chunk if pass_no == 1 else MOMENT_MAX_GRIDS
    count = max(1, -(-len(grids) // max(1, size)))
    step = -(-len(grids) // count)
    return [Chunk(batch["batch"], i, grids[j:j + step])
            for i, j in enumerate(range(0, len(grids), step))]


def cache_dir(game_id, pass_no):
    return config.FRAMES_DIR / game_id / f"pass{pass_no}" / "analysis"


def pending_grids(game_id, pass_no):
    """How many grids of a pass are not logged yet (for cost estimates)."""
    manifest = load_manifest(game_id, pass_no)
    done = set(load_progress(game_id).get(f"pass{pass_no}", {}).get("done_batches", []))
    return sum(len(b["grids"]) for b in manifest["batches"] if b["batch"] not in done)


def run_pass(game, pass_no, analyzer, workers=DEFAULT_WORKERS, grids_per_chunk=GRIDS_PER_CHUNK,
             progress=None, stop=None, redo=False):
    """Analyze every batch of a pass that isn't logged yet. Returns a PassReport.

    progress(snapshot) is called from this thread after every chunk. Set the
    threading.Event `stop` to finish the requests in flight and then stop.
    """
    manifest = load_manifest(game["id"], pass_no)
    done = set() if redo else set(load_progress(game["id"]).get(f"pass{pass_no}", {}).get("done_batches", []))
    plan = {b["batch"]: plan_chunks(b, pass_no, grids_per_chunk)
            for b in manifest["batches"] if b["batch"] not in done}
    report = PassReport(pass_no, total_chunks=sum(len(c) for c in plan.values()))
    results = {batch_no: {} for batch_no in plan}
    batch_usage = {batch_no: {} for batch_no in plan}
    folder = cache_dir(game["id"], pass_no)

    todo = []
    for batch_no, chunks in plan.items():
        for chunk in chunks:
            cached = None if redo else _read_cache(folder, chunk)
            if cached is None:
                todo.append(chunk)
                continue
            results[batch_no][chunk.index] = cached["entries"]
            report.cached_chunks += 1
        _save_if_complete(game, pass_no, plan, results, batch_usage, report, batch_no)

    start = time.time()
    if progress:
        progress(report.snapshot(0.0))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_analyze_chunk, analyzer, game, pass_no, chunk, folder): chunk for chunk in todo}
        try:
            _collect(futures, game, pass_no, plan, results, batch_usage, report, progress, stop, start)
        except BaseException:           # e.g. the app page was reloaded: don't start new requests
            _cancel(futures)
            raise
    report.seconds = time.time() - start
    return report


def _collect(futures, game, pass_no, plan, results, batch_usage, report, progress, stop, start):
    """Take chunk results as they come in, and save each batch once it is complete."""
    for future in as_completed(futures):
        chunk = futures[future]
        try:
            entries, usage = future.result()
        except CancelledError:
            continue
        except FatalAnalysisError as err:
            report.fatal = str(err)
            _cancel(futures)
            continue
        except Exception as err:        # one bad chunk must not stop the others
            report.failed.append((chunk.name, str(err) or err.__class__.__name__))
        else:
            results[chunk.batch][chunk.index] = entries
            _add(report.usage, usage)
            _add(batch_usage[chunk.batch], usage)
            report.done_chunks += 1
            _save_if_complete(game, pass_no, plan, results, batch_usage, report, chunk.batch)
        if progress:
            progress(report.snapshot(time.time() - start))
        if stop is not None and stop.is_set() and not report.stopped:
            report.stopped = True
            _cancel(futures)


def _analyze_chunk(analyzer, game, pass_no, chunk, folder):
    """Run one chunk and keep its answer on disk straight away (it was paid for).

    Analyzers with an `analyze` method also report token usage.
    """
    batch = {"batch": chunk.batch, "grids": chunk.grids}
    if hasattr(analyzer, "analyze"):
        entries, usage = analyzer.analyze(game, pass_no, batch)
    else:
        entries, usage = analyzer.analyze_batch(game, pass_no, batch), {}
    _write_cache(folder, chunk, entries, usage)
    return entries, usage


def _save_if_complete(game, pass_no, plan, results, batch_usage, report, batch_no):
    """Save a batch to the log once every one of its chunks is back."""
    chunks = plan[batch_no]
    if len(results[batch_no]) < len(chunks):
        return
    entries = [e for chunk in chunks for e in results[batch_no][chunk.index]]
    if not entries:
        report.failed.append((f"batch {batch_no}", "no frames came back"))
        return
    try:
        result = save_entries(game, pass_no, batch_no, entries, strict=False,
                              usage=batch_usage[batch_no] or None)
    except (AnalysisError, OSError) as err:
        report.failed.append((f"batch {batch_no}", str(err)))
        return
    report.saved_batches.append(batch_no)
    report.problems += [f"batch {batch_no}: {p}" for p in result["problems"]]


def _cancel(futures):
    """Cancel requests that haven't started (the ones running finish normally)."""
    for future in futures:
        future.cancel()


def _add(total, usage):
    for key, value in (usage or {}).items():
        total[key] = total.get(key, 0) + value


def _read_cache(folder, chunk):
    path = folder / f"{chunk.name}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    # Only trust a cached answer for exactly the same frames.
    stamps = [c["timestamp"] for g in chunk.grids for c in g["cells"]]
    return data if data.get("timestamps") == stamps else None


def _write_cache(folder, chunk, entries, usage):
    folder.mkdir(parents=True, exist_ok=True)
    stamps = [c["timestamp"] for g in chunk.grids for c in g["cells"]]
    data = {"timestamps": stamps, "entries": entries, "usage": usage, "saved_at": time.time()}
    tmp = folder / f".{chunk.name}.tmp"
    tmp.write_text(json.dumps(data))
    tmp.replace(folder / f"{chunk.name}.json")
