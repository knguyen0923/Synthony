import os
import threading
from contextlib import contextmanager
from typing import Optional

MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))

# How long a queued job will wait for a free slot before giving up and
# failing cleanly. run_arrange_pipeline() runs on Starlette's shared anyio
# threadpool (also used to serve the /storage/*.musicxml static mount), so
# an unbounded wait here would let enough queued jobs pin every thread in
# that pool and starve the whole app, not just the job queue. 30 minutes is
# generous enough that it only trips under genuine sustained overload, not
# normal queueing.
JOB_QUEUE_TIMEOUT_SECONDS = float(os.environ.get("JOB_QUEUE_TIMEOUT_SECONDS", "1800"))

_slots = threading.Semaphore(MAX_CONCURRENT_JOBS)


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
