# Production Hardening (personal/demo scope) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Synthony the engineering hygiene a personal/demo project
should have — CI, real logging, a concurrency guardrail so a burst of
requests can't overload the host machine, and an easy Docker-based
local-run story — without building infrastructure (auth, rate limiting,
a distributed job queue) that only matters for a public, multi-tenant
service.

**Architecture:** Four additive, independent layers on top of the
existing FastAPI app: a GitHub Actions workflow, a `logging` setup wired
into `app/main.py`/`app/arrange_pipeline.py`, a `threading.Semaphore`-based
job-slot limiter (`app/concurrency.py`) wrapping the heavy-compute
sections of `/transcribe` and `run_arrange_pipeline`, and a
Dockerfile/docker-compose pairing. None of this touches the
transcription/arrangement/difficulty pipeline itself.

**Tech Stack:** Python stdlib `logging` and `threading` (no new runtime
dependencies), GitHub Actions, Docker/docker-compose.

**Spec:** `docs/superpowers/specs/2026-09-11-production-hardening-design.md`

## Global Constraints

- No new Python runtime dependencies — `logging` and `threading` are
  stdlib. No new frontend dependencies either.
- No auth, no rate limiting beyond the concurrency cap, no persistent or
  distributed job queue — out of scope per the spec's Non-Goals (the user
  has confirmed Synthony is a personal/demo project, not a public
  service).
- `MAX_CONCURRENT_JOBS` defaults to 2 and is overridable via an env var of
  the same name — applies process-wide, consistent with the existing
  single-process, in-memory `app/jobs.py` design.
- The CI backend job must reuse the exact install recipe already
  documented in `README.md`'s "Backend" section (pre-install
  numpy/scipy/cython/mido/`setuptools<81`, then
  `pip install --no-build-isolation -r requirements.txt`) — madmom's sdist
  build depends on this exact order.
- Docker image builds are not wired into CI — Demucs/torch/madmom make
  build time impractical for per-push CI at this project's scale. Verify
  Task 4 manually via `docker compose build && docker compose up`.
- Per organization policy, nothing in this plan writes to a production or
  live environment. Docker/compose output here is for local use only.

---

## File Structure

- Create: `.github/workflows/ci.yml`
- Create: `backend/app/logging_config.py`
- Create: `backend/tests/test_logging_config.py`
- Modify: `backend/app/main.py` (logging setup + exception-clause split)
- Modify: `backend/app/arrange_pipeline.py` (logging)
- Modify: `backend/tests/test_api.py` (logging-behavior tests)
- Create: `backend/app/concurrency.py`
- Create: `backend/tests/test_concurrency.py`
- Modify: `backend/app/jobs.py` (`Job`'s default status becomes `"queued"`)
- Modify: `backend/tests/test_jobs.py`
- Modify: `backend/app/main.py` (again, in Task 3 — wires `job_slot` into `/transcribe`)
- Modify: `backend/app/arrange_pipeline.py` (again, in Task 3 — wires `job_slot` into `run_arrange_pipeline`)
- Modify: `backend/tests/test_arrange_pipeline.py` (queued/slot-wait test)
- Modify: `frontend/src/api/arrange.ts` (`ArrangeStage`/`STAGE_LABELS` gain `"queued"`)
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`
- Create: `docker-compose.yml`

---

## Task 1: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:** None — this task produces no importable code, just CI
config consumed by GitHub Actions.

- [ ] **Step 1: Write the workflow file**

```yaml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install system dependencies
        run: sudo apt-get update && sudo apt-get install -y ffmpeg fluidsynth

      - name: Install Python dependencies
        working-directory: backend
        run: |
          python -m pip install --upgrade pip
          pip install "numpy>=1.26.4,<2.0" scipy cython mido "setuptools<81"
          pip install --no-build-isolation -r requirements.txt

      - name: Run backend test suite
        working-directory: backend
        run: python -m pytest -q

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "18"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        working-directory: frontend
        run: npm ci

      - name: Lint
        working-directory: frontend
        run: npm run lint

      - name: Build
        working-directory: frontend
        run: npm run build
```

- [ ] **Step 2: Validate the YAML parses**

This repo's local Python has no `pyyaml` installed and there's no `gh`
CLI available in this environment, so validate structurally instead:

Run: `python3 -c "import json, sys; [print('no tabs') if '\t' not in open('.github/workflows/ci.yml').read() else sys.exit(1)]"`
Expected: prints `no tabs` (YAML is indentation-sensitive; a stray tab
character is the most common hand-authoring mistake). Also visually
re-read the file for consistent 2-space indentation under each `steps:`
list.

- [ ] **Step 3: Confirm the exact commands succeed locally first**

The workflow's backend steps are exactly this repo's documented install
recipe — confirm they still work before trusting CI will pass on first
push:

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all tests pass (227 passed, per the last full run on this
branch).

Run: `cd frontend && npm run lint`
Expected: no output, exit code 0.

Note: `npm run build` cannot be verified on this machine locally — this
repo's local Node is v16.20.2, and Vite 5 requires Node 17.4+/18 (fails
with `crypto$2.getRandomValues is not a function`). The workflow's
`setup-node` step pins Node 18, so this only gets a real check from an
actual CI run, not a local dry run. Don't skip pushing and watching the
first Actions run for this reason.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run backend pytest and frontend build/lint on push"
```

---

## Task 2: Structured logging

**Files:**
- Create: `backend/app/logging_config.py`
- Create: `backend/tests/test_logging_config.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/arrange_pipeline.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `configure_logging() -> None` in `app.logging_config` — call
  it once at process startup; safe to call again (e.g. from a test) since
  it passes `force=True` to `logging.basicConfig`.

- [ ] **Step 1: Write the failing tests for `configure_logging`**

Create `backend/tests/test_logging_config.py`:

```python
import logging

from app.logging_config import configure_logging


def test_configure_logging_defaults_to_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging()
    assert logging.getLogger().level == logging.INFO


def test_configure_logging_reads_log_level_env_var(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    configure_logging()
    assert logging.getLogger().level == logging.DEBUG
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_logging_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.logging_config'`

- [ ] **Step 3: Implement `app/logging_config.py`**

```python
import logging
import os


def configure_logging() -> None:
    """Configure the root logger once at process startup. Level is
    overridable via the LOG_LEVEL env var (e.g. LOG_LEVEL=DEBUG) for local
    debugging. Uses force=True so calling this more than once (e.g. from a
    test that wants a fresh level) actually takes effect, instead of
    logging.basicConfig's normal "no-op after the first call" behavior."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_logging_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/logging_config.py backend/tests/test_logging_config.py
git commit -m "feat: add configurable logging setup"
```

- [ ] **Step 6: Write the failing tests for exception logging in `/transcribe`**

Add to `backend/tests/test_api.py` (near the other `transcribe` failure
tests, after `test_transcribe_no_pitched_content_cleans_up_orphan_song_dir`):

```python
import logging

import pytest


def test_transcribe_unexpected_failure_logs_the_exception(monkeypatch, caplog, synthetic_piano_wav):
    import app.main as main_module

    def boom(path):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(main_module, "transcribe_piano_audio_to_notes", boom)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        with open(synthetic_piano_wav, "rb") as f:
            with pytest.raises(RuntimeError, match="model exploded"):
                client.post(
                    "/transcribe",
                    files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
                )

    assert "transcribe failed" in caplog.text


def test_transcribe_expected_validation_failure_does_not_log_an_error(monkeypatch, caplog, synthetic_piano_wav):
    """A 422 "no pitched content" outcome is expected control flow, not a
    bug — it shouldn't produce an ERROR-level stack trace the way a genuine
    crash does."""
    import app.main as main_module
    from app.transcription.audio_to_midi import PianoTranscriptionResult

    monkeypatch.setattr(
        main_module,
        "transcribe_piano_audio_to_notes",
        lambda path: PianoTranscriptionResult(notes=[], pedal_events=[]),
    )

    with caplog.at_level(logging.ERROR, logger="app.main"):
        with open(synthetic_piano_wav, "rb") as f:
            response = client.post(
                "/transcribe",
                files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
            )

    assert response.status_code == 422
    assert "transcribe failed" not in caplog.text
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k "logs_the_exception or does_not_log_an_error" -v`
Expected: FAIL — `test_transcribe_unexpected_failure_logs_the_exception`
fails because `"transcribe failed"` never appears in `caplog.text` (the
current bare `except Exception:` block has no logging call at all).

- [ ] **Step 8: Wire logging into `app/main.py`**

Modify `backend/app/main.py` — add the import and logger near the top
(after the existing imports, before `MAX_DURATION_SECONDS`):

```python
from app.logging_config import configure_logging
```

(add this alongside the other `from app...` imports, e.g. right after
`from app.export import export_musicxml`)

Then, right after `STORAGE_ROOT.mkdir(parents=True, exist_ok=True)` and
before `app = FastAPI()`:

```python
configure_logging()
logger = logging.getLogger(__name__)
```

(add `import logging` to the top-of-file stdlib imports, alongside `os`,
`shutil`, `tempfile`)

Then split `transcribe()`'s single `except Exception:` block into two —
replace:

```python
    except Exception:
        # song_dir() already created dest_dir before any of the above ran;
        # any failure past that point (a rejected upload, a duration-cap
        # violation, no pitched content, a downloaded-but-unusable YouTube
        # file, ...) must not leave an orphan directory — or, for YouTube
        # input, an orphan downloaded audio file — behind under STORAGE_ROOT.
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise
```

with:

```python
    except HTTPException:
        # Expected control flow (bad/no input, duration cap, no pitched
        # content) — cleanup happens the same as any other failure, but
        # this isn't a bug, so it doesn't get an ERROR-level stack trace.
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise
    except Exception:
        # song_dir() already created dest_dir before any of the above ran;
        # any failure past that point (a downloaded-but-unusable YouTube
        # file, an unexpected model crash, ...) must not leave an orphan
        # directory — or, for YouTube input, an orphan downloaded audio
        # file — behind under STORAGE_ROOT.
        logger.exception("transcribe failed for song_id=%s", song_id)
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k "logs_the_exception or does_not_log_an_error" -v`
Expected: PASS (2 passed)

- [ ] **Step 10: Run the full backend suite to check for regressions**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all tests pass (227+, plus the new ones from this task)

- [ ] **Step 11: Commit**

```bash
git add backend/app/main.py backend/tests/test_api.py
git commit -m "feat: log unexpected transcribe failures, not just expected validation errors"
```

- [ ] **Step 12: Write the failing test for exception logging in the arrange pipeline**

Add to `backend/tests/test_api.py`, right after
`test_arrange_job_failure_sets_failed_status_with_detail`:

```python
def test_arrange_job_failure_logs_the_exception(monkeypatch, caplog, synthetic_piano_wav):
    import app.arrange_pipeline as pipeline_module

    def boom(audio_path, output_dir):
        raise RuntimeError("separation blew up")

    monkeypatch.setattr(pipeline_module, "separate_stems", boom)

    with caplog.at_level(logging.ERROR, logger="app.arrange_pipeline"):
        with open(synthetic_piano_wav, "rb") as f:
            response = client.post("/arrange", files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")})
        job_id = response.json()["job_id"]

        result = None
        for _ in range(50):
            payload = client.get(f"/arrange/{job_id}").json()
            if payload.get("status") == "failed":
                result = payload
                break
            time.sleep(0.05)

    assert result == {"status": "failed", "detail": "separation blew up"}
    assert "arrange pipeline failed" in caplog.text
```

- [ ] **Step 13: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k test_arrange_job_failure_logs_the_exception -v`
Expected: FAIL — `"arrange pipeline failed"` never appears in
`caplog.text` (no logging call exists yet).

- [ ] **Step 14: Wire logging into `app/arrange_pipeline.py`**

Modify `backend/app/arrange_pipeline.py` — add near the top, after the
existing imports:

```python
import logging

logger = logging.getLogger(__name__)
```

Then replace the existing `except Exception as exc:` block:

```python
    except Exception as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        set_failed(job_id, str(exc))
```

with:

```python
    except Exception as exc:
        logger.exception("arrange pipeline failed for job_id=%s song_id=%s", job_id, song_id)
        shutil.rmtree(dest_dir, ignore_errors=True)
        set_failed(job_id, str(exc))
```

- [ ] **Step 15: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k test_arrange_job_failure_logs_the_exception -v`
Expected: PASS

- [ ] **Step 16: Run the full backend suite to check for regressions**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all tests pass

- [ ] **Step 17: Commit**

```bash
git add backend/app/arrange_pipeline.py backend/tests/test_api.py
git commit -m "feat: log arrange pipeline failures"
```

---

## Task 3: Concurrency guardrail

**Files:**
- Create: `backend/app/concurrency.py`
- Create: `backend/tests/test_concurrency.py`
- Modify: `backend/app/jobs.py`
- Modify: `backend/tests/test_jobs.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/arrange_pipeline.py`
- Modify: `backend/tests/test_arrange_pipeline.py`
- Modify: `frontend/src/api/arrange.ts`

**Interfaces:**
- Produces: `job_slot(blocking: bool = True, timeout: Optional[float] = None)`
  — a context manager in `app.concurrency`, and
  `NoJobSlotAvailable(Exception)` in the same module.
- Produces: `MAX_CONCURRENT_JOBS: int` (module-level constant in
  `app.concurrency`, read from the `MAX_CONCURRENT_JOBS` env var, default
  `2`) and `_slots: threading.Semaphore` (monkeypatchable by tests).
- Modifies: `Job`'s default `status` in `app.jobs` from `"separating"` to
  `"queued"`.
- Consumes (from Task 2): the `HTTPException`/`Exception` exception-clause
  split already in `app.main.transcribe`, and the `logger` already defined
  in both `app.main` and `app.arrange_pipeline`.

- [ ] **Step 1: Write the failing tests for `app/concurrency.py`**

Create `backend/tests/test_concurrency.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_concurrency.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.concurrency'`

- [ ] **Step 3: Implement `app/concurrency.py`**

```python
import os
import threading
from contextlib import contextmanager
from typing import Optional

MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_concurrency.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/concurrency.py backend/tests/test_concurrency.py
git commit -m "feat: add a job-slot concurrency limiter"
```

- [ ] **Step 6: Write the failing test for `/transcribe` rejecting when busy**

Add to `backend/tests/test_api.py`, after the new logging tests from
Task 2:

```python
def test_transcribe_returns_503_when_no_job_slot_available(monkeypatch, synthetic_piano_wav):
    import threading

    import app.concurrency as concurrency_module

    monkeypatch.setattr(concurrency_module, "_slots", threading.Semaphore(1))

    with concurrency_module.job_slot():  # occupy the only slot
        with open(synthetic_piano_wav, "rb") as f:
            response = client.post(
                "/transcribe",
                files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
            )

    assert response.status_code == 503
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k test_transcribe_returns_503_when_no_job_slot_available -v`
Expected: FAIL — currently returns 200 (or 422/whatever the real pipeline
does), never 503, since nothing wraps `/transcribe`'s heavy section in a
job slot yet.

- [ ] **Step 8: Wire `job_slot` into `app/main.py`'s `transcribe()`**

Add the import (alongside the other `from app...` imports):

```python
from app.concurrency import NoJobSlotAvailable, job_slot
```

Then wrap the heavy-compute section of `transcribe()` — replace:

```python
        transcription = transcribe_piano_audio_to_notes(str(ingested.path))
        notes = transcription.notes
        if not notes:
            raise HTTPException(status_code=422, detail="No pitched content detected")

        beat_map = detect_beat_map(str(ingested.path))

        title = ingested.title
        score = notes_to_grand_staff(
            notes, title=title, beat_map=beat_map, pedal_events=transcription.pedal_events
        )
        variants = generate_variants(score)

        for tier, variant_score in (
            ("easy", variants.easy),
            ("medium", variants.medium),
            ("hard", variants.hard),
        ):
            export_musicxml(variant_score, dest_dir / f"{tier}.musicxml")

        write_metadata(song_id, title=title, source_type=ingested.source_type, source_url=ingested.source_url)
        evict_oldest_songs()
```

with:

```python
        title = ingested.title
        try:
            with job_slot(blocking=False):
                transcription = transcribe_piano_audio_to_notes(str(ingested.path))
                notes = transcription.notes
                if not notes:
                    raise HTTPException(status_code=422, detail="No pitched content detected")

                beat_map = detect_beat_map(str(ingested.path))

                score = notes_to_grand_staff(
                    notes, title=title, beat_map=beat_map, pedal_events=transcription.pedal_events
                )
                variants = generate_variants(score)

                for tier, variant_score in (
                    ("easy", variants.easy),
                    ("medium", variants.medium),
                    ("hard", variants.hard),
                ):
                    export_musicxml(variant_score, dest_dir / f"{tier}.musicxml")
        except NoJobSlotAvailable as exc:
            logger.warning("transcribe rejected for song_id=%s: %s", song_id, exc)
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        write_metadata(song_id, title=title, source_type=ingested.source_type, source_url=ingested.source_url)
        evict_oldest_songs()
```

(`title = ingested.title` moved above the `try` since it's needed by the
final `return` statement below regardless of which branch ran.)

- [ ] **Step 9: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k test_transcribe_returns_503_when_no_job_slot_available -v`
Expected: PASS

- [ ] **Step 10: Run the full backend suite to check for regressions**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all tests pass — in particular, re-check
`test_transcribe_with_file_upload_returns_all_three_difficulties` and the
other pre-existing `/transcribe` tests still pass unchanged (the default
`MAX_CONCURRENT_JOBS=2` and a fresh semaphore per test process means they
never contend for a slot).

- [ ] **Step 11: Commit**

```bash
git add backend/app/main.py backend/tests/test_api.py
git commit -m "feat: reject /transcribe with 503 when no job slot is free"
```

- [ ] **Step 12: Write the failing test for the arrange pipeline waiting on a job slot**

Add to `backend/tests/test_arrange_pipeline.py`:

```python
import threading
import time

from app.arrange_pipeline import run_arrange_pipeline
from app.jobs import create_job, get_job
from app.separation.types import Stems


def test_run_arrange_pipeline_waits_for_a_job_slot(tmp_path, monkeypatch):
    import app.arrange_pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "_slots", threading.Semaphore(1))

    fake_notes = [NoteEvent(start=0.0, end=0.5, pitch=72)]
    fake_lh_notes = [NoteEvent(start=0.0, end=0.5, pitch=48)]
    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=tmp_path / "vocals.wav", drums=tmp_path / "drums.wav",
            bass=tmp_path / "bass.wav", other=tmp_path / "other.wav",
        ),
    )
    monkeypatch.setattr(pipeline_module, "mix_wav_files", lambda a, b, dest: dest)
    monkeypatch.setattr(pipeline_module, "extract_melody_notes", lambda audio_path: fake_notes)
    monkeypatch.setattr(pipeline_module, "extract_lh_notes", lambda audio_path: fake_lh_notes)
    monkeypatch.setattr(pipeline_module, "detect_key_and_tempo", lambda audio_path: ((0, "major"), 0.5))
    monkeypatch.setattr(pipeline_module, "detect_beat_map", lambda audio_path: BeatMap.constant(0.5))

    job_id = create_job()
    assert get_job(job_id).status == "queued"

    # Occupy the only slot from this thread so the pipeline (run in its own
    # thread below) has to actually wait for it.
    from app.concurrency import job_slot as real_job_slot

    holding = threading.Event()
    release_holder = threading.Event()

    def hold_slot():
        with real_job_slot():
            holding.set()
            release_holder.wait(timeout=2.0)

    holder_thread = threading.Thread(target=hold_slot)
    holder_thread.start()
    holding.wait(timeout=1.0)

    pipeline_thread = threading.Thread(
        target=run_arrange_pipeline,
        kwargs=dict(
            job_id=job_id, audio_path="fake.wav", title="Song",
            source_type="upload", source_url=None, song_id="fake-song-id",
            dest_dir=tmp_path,
        ),
    )
    pipeline_thread.start()

    time.sleep(0.1)
    assert get_job(job_id).status == "queued"  # still waiting on the held slot

    release_holder.set()
    holder_thread.join()
    pipeline_thread.join(timeout=5.0)

    assert get_job(job_id).status == "done"
```

- [ ] **Step 13: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -k test_run_arrange_pipeline_waits_for_a_job_slot -v`
Expected: FAIL — `run_arrange_pipeline` doesn't reference any job slot
yet, so the job never actually waits; `get_job(job_id).status` moves past
`"queued"` immediately instead of staying there while the holder thread
has the slot.

- [ ] **Step 14: Wire `job_slot` into `app/arrange_pipeline.py`**

Add the import (alongside the other `from app...` imports):

```python
from app.concurrency import job_slot
```

Then wrap the pipeline body — replace:

```python
    try:
        set_status(job_id, "separating")
        stems = separate_stems(audio_path, dest_dir / "stems")

        set_status(job_id, "extracting_melody")
        melody_notes = extract_melody_notes(str(stems.vocals))

        set_status(job_id, "detecting_key")
        harmony_path = mix_wav_files(stems.bass, stems.other, dest_dir / "stems" / "harmony.wav")
        detected_key, seconds_per_quarter = detect_key_and_tempo(str(harmony_path))
        beat_map = detect_beat_map(str(harmony_path))

        set_status(job_id, "arranging")
        lh_variants = _lh_variants(str(harmony_path), seconds_per_quarter, beat_map)
        rh_variants = _rh_variants(melody_notes, seconds_per_quarter, beat_map)

        difficulties = {}
        key_signature = key_signature_from_tonic(*detected_key)
        for tier in ("easy", "medium", "hard"):
            score = build_grand_staff_score(rh_variants[tier], lh_variants[tier], title=title, key_signature=key_signature)
            export_musicxml(score, dest_dir / f"{tier}.musicxml")
            difficulties[tier] = {"musicxml_url": f"/storage/{song_id}/{tier}.musicxml"}

        write_metadata(song_id, title=title, source_type=source_type, source_url=source_url, pipeline="arrange")
        evict_oldest_songs()

        set_result(job_id, {"song_id": song_id, "title": title, "difficulties": difficulties})
    except Exception as exc:
        logger.exception("arrange pipeline failed for job_id=%s song_id=%s", job_id, song_id)
        shutil.rmtree(dest_dir, ignore_errors=True)
        set_failed(job_id, str(exc))
```

with:

```python
    try:
        logger.info("job %s: waiting for a free job slot", job_id)
        with job_slot(blocking=True):
            set_status(job_id, "separating")
            stems = separate_stems(audio_path, dest_dir / "stems")

            set_status(job_id, "extracting_melody")
            melody_notes = extract_melody_notes(str(stems.vocals))

            set_status(job_id, "detecting_key")
            harmony_path = mix_wav_files(stems.bass, stems.other, dest_dir / "stems" / "harmony.wav")
            detected_key, seconds_per_quarter = detect_key_and_tempo(str(harmony_path))
            beat_map = detect_beat_map(str(harmony_path))

            set_status(job_id, "arranging")
            lh_variants = _lh_variants(str(harmony_path), seconds_per_quarter, beat_map)
            rh_variants = _rh_variants(melody_notes, seconds_per_quarter, beat_map)

            difficulties = {}
            key_signature = key_signature_from_tonic(*detected_key)
            for tier in ("easy", "medium", "hard"):
                score = build_grand_staff_score(rh_variants[tier], lh_variants[tier], title=title, key_signature=key_signature)
                export_musicxml(score, dest_dir / f"{tier}.musicxml")
                difficulties[tier] = {"musicxml_url": f"/storage/{song_id}/{tier}.musicxml"}

            write_metadata(song_id, title=title, source_type=source_type, source_url=source_url, pipeline="arrange")
            evict_oldest_songs()

        set_result(job_id, {"song_id": song_id, "title": title, "difficulties": difficulties})
    except Exception as exc:
        logger.exception("arrange pipeline failed for job_id=%s song_id=%s", job_id, song_id)
        shutil.rmtree(dest_dir, ignore_errors=True)
        set_failed(job_id, str(exc))
```

Note: `job_id` starts (via `create_job()`, changed in the next step)
already in `"queued"` status, so no explicit `set_status(job_id,
"queued")` call is needed here — the default covers the wait.

- [ ] **Step 15: Change `Job`'s default status to `"queued"`**

First, update the existing test that locks in the old default. In
`backend/tests/test_jobs.py`, replace:

```python
def test_create_job_starts_in_separating_status():
    job_id = create_job()
    job = get_job(job_id)
    assert job.status == "separating"
    assert job.result is None
    assert job.detail is None
```

with:

```python
def test_create_job_starts_in_queued_status():
    job_id = create_job()
    job = get_job(job_id)
    assert job.status == "queued"
    assert job.result is None
    assert job.detail is None
```

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_jobs.py -k test_create_job_starts_in_queued_status -v`
Expected: FAIL — the `Job` dataclass still defaults to `"separating"`.

In `backend/app/jobs.py`, change:

```python
@dataclass
class Job:
    status: str = "separating"
    result: Optional[dict] = None
    detail: Optional[str] = None
```

to:

```python
@dataclass
class Job:
    status: str = "queued"
    result: Optional[dict] = None
    detail: Optional[str] = None
```

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_jobs.py -v`
Expected: PASS (all tests in this file)

- [ ] **Step 16: Run the new arrange-pipeline test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -k test_run_arrange_pipeline_waits_for_a_job_slot -v`
Expected: PASS

- [ ] **Step 17: Run the full backend suite to check for regressions**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all tests pass. In particular, confirm
`test_arrange_full_job_lifecycle_returns_transcribe_shaped_result` and
`test_arrange_job_failure_sets_failed_status_with_detail` (from
`test_api.py`) still pass — they exercise `/arrange` end-to-end through
the real (non-monkeypatched) `MAX_CONCURRENT_JOBS=2` semaphore, which has
plenty of room for one job.

- [ ] **Step 18: Add `"queued"` to the frontend's `ArrangeStage` type**

The backend can now report a `"queued"` status while a job waits for a
free slot. `frontend/src/api/arrange.ts`'s `STAGE_LABELS` is typed as
`Record<ArrangeStage, string>`, so TypeScript requires every union member
to have a label — omitting `"queued"` here would fail `tsc` (part of
`npm run build`), not just look incomplete.

In `frontend/src/api/arrange.ts`, change:

```typescript
type ArrangeStage = "separating" | "extracting_melody" | "detecting_key" | "arranging";

const STAGE_LABELS: Record<ArrangeStage, string> = {
  separating: "Separating vocals and instruments…",
  extracting_melody: "Extracting the melody…",
  detecting_key: "Detecting the key…",
  arranging: "Arranging the accompaniment…",
};
```

to:

```typescript
type ArrangeStage = "queued" | "separating" | "extracting_melody" | "detecting_key" | "arranging";

const STAGE_LABELS: Record<ArrangeStage, string> = {
  queued: "Waiting for a free processing slot…",
  separating: "Separating vocals and instruments…",
  extracting_melody: "Extracting the melody…",
  detecting_key: "Detecting the key…",
  arranging: "Arranging the accompaniment…",
};
```

- [ ] **Step 19: Verify the frontend type-checks**

This repo's local Node (v16.20.2) can't run Vite 5's build at all (see
Task 1, Step 3) — this change can only be verified by an actual `tsc`
run. If a Node 18+ environment is available:

Run: `cd frontend && npm run build`
Expected: succeeds (no `tsc` errors about `STAGE_LABELS` missing a
`"queued"` key). Otherwise, defer this check to the CI run from Task 1,
and to a manual visual check once Task 4's Docker frontend image (built
with Node 18) is running.

- [ ] **Step 20: Commit**

```bash
git add backend/app/arrange_pipeline.py backend/app/jobs.py backend/tests/test_jobs.py backend/tests/test_arrange_pipeline.py frontend/src/api/arrange.ts
git commit -m "feat: make /arrange wait for a free job slot, report queued status"
```

---

## Task 4: Docker local-run story

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`
- Create: `docker-compose.yml`

**Interfaces:** None — this task produces no importable code.

- [ ] **Step 1: Write `backend/.dockerignore`**

```
.venv/
storage/
scripts/quality_harness/assets/
scripts/quality_harness/output/
__pycache__/
*.pyc
```

- [ ] **Step 2: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.11-slim

# ffmpeg: yt-dlp needs it to extract audio from YouTube-link input.
# fluidsynth: only needed by the test suite's synthetic_piano_note_wav
# fixture; harmless to include so `pytest` is runnable inside the image.
# build-essential + git: madmom's sdist compiles Cython extensions and is
# installed straight from its GitHub main branch (see requirements.txt).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fluidsynth build-essential git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Same two-step install as README's "Backend" section: madmom's setup.py
# imports numpy/scipy/Cython/mido directly (not declared as PEP 517 build
# requirements), so they must already be present, and the install itself
# needs --no-build-isolation.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "numpy>=1.26.4,<2.0" scipy cython mido "setuptools<81" \
    && pip install --no-cache-dir --no-build-isolation -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Write `frontend/.dockerignore`**

```
node_modules/
dist/
```

- [ ] **Step 4: Write `frontend/Dockerfile`**

```dockerfile
FROM node:18-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Baked in at build time (Vite inlines import.meta.env at build, not at
# runtime) — override with docker-compose's build arg for a non-default
# backend location.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

- [ ] **Step 5: Write `docker-compose.yml`**

```yaml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - backend_storage:/app/storage
    environment:
      - SPOTIFY_CLIENT_ID=${SPOTIFY_CLIENT_ID:-}
      - SPOTIFY_CLIENT_SECRET=${SPOTIFY_CLIENT_SECRET:-}
      - MAX_CONCURRENT_JOBS=${MAX_CONCURRENT_JOBS:-2}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}

  frontend:
    build:
      context: ./frontend
      args:
        VITE_API_BASE_URL: http://localhost:8000
    ports:
      - "5173:80"
    depends_on:
      - backend

volumes:
  backend_storage:
```

- [ ] **Step 6: Build the backend image**

This pulls Demucs/torch/madmom and compiles madmom's Cython extensions —
expect this to take a while (well past typical shell timeouts). Run it in
the background and poll rather than blocking on it:

Run: `docker compose build backend` (in the background; check with
`docker compose images` / `docker compose logs` once it's done)
Expected: image builds successfully, ending with the `uvicorn` `CMD` line
in the final layer.

- [ ] **Step 7: Build the frontend image**

Run: `docker compose build frontend`
Expected: builds successfully; much faster than the backend image (just
`npm ci` + `vite build`, no compiled ML dependencies).

- [ ] **Step 8: Bring the stack up and smoke-test it**

Run: `docker compose up -d`

Run: `curl -s http://localhost:8000/health`
Expected: `{"status":"ok"}`

Run: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173`
Expected: `200`

Run: `docker compose down`

- [ ] **Step 9: Commit**

```bash
git add backend/Dockerfile backend/.dockerignore frontend/Dockerfile frontend/.dockerignore docker-compose.yml
git commit -m "build: add Dockerfile/docker-compose for local-only container runs"
```
