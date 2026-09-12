import threading
import time

import pytest

import app.concurrency as concurrency_module
from app.concurrency import NoJobSlotAvailable, job_slot


def test_job_slot_runs_the_block_and_releases_afterward(monkeypatch):
    monkeypatch.setattr(concurrency_module, "_slots", threading.Semaphore(1))

    with job_slot():
        pass

    # The slot must be free again — a second non-blocking acquire succeeds.
    with job_slot(blocking=False):
        pass


def test_job_slot_raises_when_no_slot_available_non_blocking(monkeypatch):
    monkeypatch.setattr(concurrency_module, "_slots", threading.Semaphore(1))

    with job_slot():  # occupies the only slot
        with pytest.raises(NoJobSlotAvailable):
            with job_slot(blocking=False):
                pass


def test_job_slot_waits_up_to_timeout_then_raises(monkeypatch):
    monkeypatch.setattr(concurrency_module, "_slots", threading.Semaphore(1))

    with job_slot():  # occupies the only slot, never released within the test
        start = time.monotonic()
        with pytest.raises(NoJobSlotAvailable):
            with job_slot(blocking=True, timeout=0.1):
                pass
        elapsed = time.monotonic() - start

    assert elapsed >= 0.1


def test_job_slot_waits_for_a_slot_freed_by_another_thread(monkeypatch):
    monkeypatch.setattr(concurrency_module, "_slots", threading.Semaphore(1))
    entered = threading.Event()

    def hold_then_release():
        with job_slot():
            entered.set()
            time.sleep(0.1)

    holder = threading.Thread(target=hold_then_release)
    holder.start()
    entered.wait(timeout=1.0)

    start = time.monotonic()
    with job_slot(blocking=True, timeout=1.0):
        elapsed = time.monotonic() - start

    holder.join()
    assert elapsed >= 0.05  # actually waited for the other thread's release
