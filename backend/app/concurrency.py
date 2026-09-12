import os
import threading
from contextlib import contextmanager
from typing import Optional

def _read_max_concurrent_jobs() -> int:
    raw = os.environ.get("MAX_CONCURRENT_JOBS")
    if raw is None:
        return 2
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"MAX_CONCURRENT_JOBS must be a positive integer, got {raw!r}") from None
    if value < 1:
        raise ValueError(f"MAX_CONCURRENT_JOBS must be a positive integer, got {raw!r}")
    return value


MAX_CONCURRENT_JOBS = _read_max_concurrent_jobs()

# Bounds how long a queued job will wait for a free slot before giving up
# and failing cleanly, turning an otherwise-indefinite wait into a wait of
# at most this many seconds. This is only a bound against a hang lasting
# forever — it is NOT by itself a guarantee against threadpool exhaustion:
# run_arrange_pipeline() runs on Starlette's BackgroundTasks, which share
# anyio's default 40-thread pool with other sync work in the app, so enough
# simultaneously-queued /arrange jobs can still pin every thread in that
# pool for up to this many seconds each under sustained heavy load. 30
# minutes is generous enough that it only trips under genuine sustained
# overload, not normal queueing.
JOB_QUEUE_TIMEOUT_SECONDS = float(os.environ.get("JOB_QUEUE_TIMEOUT_SECONDS", "1800"))

_slots = threading.BoundedSemaphore(MAX_CONCURRENT_JOBS)


class NoJobSlotAvailable(Exception):
    """Raised when a job slot can't be acquired (immediately, when
    blocking=False; after `timeout` seconds, when a timeout is given)."""


@contextmanager
def job_slot(blocking: bool = True, timeout: Optional[float] = None):
    """Acquire one of MAX_CONCURRENT_JOBS shared slots for the duration of
    a heavy transcription/arrangement job, so a burst of requests can't
    launch unbounded simultaneous Demucs/Basic Pitch/madmom/piano-
    transcription jobs on one machine."""
    acquired = _slots.acquire(blocking=blocking, timeout=timeout)
    if not acquired:
        raise NoJobSlotAvailable(f"All {MAX_CONCURRENT_JOBS} concurrent job slots are busy")
    try:
        yield
    finally:
        _slots.release()
