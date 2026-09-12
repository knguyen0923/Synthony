# Backlog and /transcribe Event-Loop Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `/transcribe`'s event-loop-blocking behavior (the last item from the pre-production-readiness backlog) and clear the 5 actionable small items parked during the production-readiness pass's final review.

**Architecture:** Three independent, surgical changes: offload `/transcribe`'s CPU-bound pipeline to a worker thread via Starlette's `run_in_threadpool` (no API/behavior change, just unblocks the event loop for concurrent requests); add the missing failure-path test for `run_arrange_pipeline`'s existing stem/dest_dir cleanup; and a small batch of independent one-line-to-few-line fixes (test log-directory isolation, a logger-restore fixture, `setup.sh --clear`, a Pydantic `/health` response model).

**Tech Stack:** Python 3.11/FastAPI (backend), pytest, Starlette's `run_in_threadpool`.

**Spec:** None — this plan documents already-diagnosed fixes directly, same as the Tier 1 bug-fix plan and the production-readiness pass's final-review fix wave. The `/transcribe` fix's design (thread-pool offload, no API change) was approved via a short in-chat bounded-brainstorm; the backlog items were fully diagnosed by the production-readiness pass's final whole-branch review.

## Global Constraints

- TDD is non-negotiable for backend Python work — write the failing test first.
- Run the full backend suite (`cd backend && ./.venv/bin/python -m pytest -v`) before any commit.
- `/transcribe`'s client-facing API and behavior must not change at all — same request/response shape, same status codes, same error handling. Only the internal event-loop-blocking mechanism changes.
- Self-hosted, single-user, local-only scope — none of this adds authentication, rate limiting, or multi-tenant concerns.

---

## File Structure

- **Modify:** `backend/app/main.py` — extract `/transcribe`'s CPU-bound pipeline into a plain function, call it via `run_in_threadpool`; add a `HealthResponse` Pydantic model to `/health` (Task 1, Task 3).
- **Modify:** `backend/tests/test_api.py` — add the event-loop non-blocking regression test (Task 1); add a logger-restore fixture to the startup-warning test (Task 3).
- **Modify:** `backend/tests/test_arrange_pipeline.py` — add the missing failure-path stem/dest_dir cleanup test (Task 2).
- **Modify:** `backend/tests/conftest.py` — redirect `LOG_DIR` to an isolated test directory, mirroring the existing `STORAGE_ROOT` redirect (Task 3).
- **Modify:** `backend/setup.sh` — add `--clear` to the venv creation command (Task 3).

No new files, no new modules.

---

### Task 1: Fix `/transcribe`'s event-loop blocking

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `starlette.concurrency.run_in_threadpool` (new import).
- Produces: a new plain (non-async) module-level function `_run_transcription_pipeline(audio_path: str, title: str, dest_dir: Path) -> None` in `app.main`, called only from the `transcribe` route handler. No signature or behavior change to `transcribe` itself.

**Context:** `/transcribe` currently runs its entire CPU-bound pipeline (piano transcription, beat detection, notation, export) synchronously inside the `async def transcribe(...)` route handler. Since there's no `await` anywhere in that block, it runs on — and blocks — the single event loop thread for its full duration, so *every other concurrent request* (including an unrelated `/health` call, or a second `/transcribe`/`/arrange`) has to wait behind it. The existing `MAX_CONCURRENT_JOBS` guardrail (via `job_slot`) can't do its job today, since a second request never even gets scheduled far enough to attempt acquiring a slot.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api.py`, after the existing health-check tests:

```python
def test_transcribe_offloads_its_pipeline_so_other_requests_are_not_blocked(monkeypatch, synthetic_piano_wav):
    """Regression test for moving /transcribe's CPU-bound pipeline onto a
    worker thread via run_in_threadpool: before that fix, the whole
    single-threaded event loop was blocked for the pipeline's full
    duration, so even an unrelated /health request had to wait behind it.
    This starts a slow /transcribe in a background thread and confirms
    /health still responds promptly while it's still "running" (the
    mocked transcription blocks on a threading.Event for up to 5s)."""
    import threading
    import time
    import app.main as main_module
    from app.transcription.audio_to_midi import PianoTranscriptionResult

    release = threading.Event()

    def _slow_then_empty(audio_path):
        release.wait(timeout=5.0)
        return PianoTranscriptionResult(notes=[], pedal_events=[])

    monkeypatch.setattr(main_module, "transcribe_piano_audio_to_notes", _slow_then_empty)

    def _make_slow_transcribe_request():
        with open(synthetic_piano_wav, "rb") as f:
            client.post("/transcribe", files={"audio_file": ("slow.wav", f, "audio/wav")})

    thread = threading.Thread(target=_make_slow_transcribe_request)
    thread.start()
    time.sleep(0.3)  # let the request actually reach the mocked, blocking call

    start = time.monotonic()
    health_response = client.get("/health")
    elapsed = time.monotonic() - start

    release.set()
    thread.join(timeout=5.0)

    assert health_response.status_code == 200
    assert elapsed < 1.0, f"/health took {elapsed:.2f}s -- /transcribe is still blocking the event loop"
```

(`client` is the module-level `TestClient(app)` already defined at the top of `test_api.py` — reuse it, don't create a new one. `synthetic_piano_wav` is the existing plain-sine-tone fixture from `conftest.py`; the mocked `transcribe_piano_audio_to_notes` ignores the audio's actual content, so the fluidsynth-free fixture is sufficient — no need for `synthetic_piano_note_wav`.)

- [ ] **Step 2: Run it, verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k offloads_its_pipeline -v`
Expected: FAIL — `elapsed` will be close to 5.0s (or the assertion times out), since `/health` currently has to wait for the blocked event loop.

- [ ] **Step 3: Implement — extract the pipeline into a plain function**

In `backend/app/main.py`, add this import:

```python
from starlette.concurrency import run_in_threadpool
```

Then change:

```python
@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio_file: Optional[UploadFile] = File(None),
    youtube_url: Optional[str] = Form(None),
    spotify_url: Optional[str] = Form(None),
) -> TranscribeResponse:
    song_id = new_song_id()
    dest_dir: Optional[Path] = None

    try:
        dest_dir = song_dir(song_id)
        ingested = await _ingest_and_validate_duration(dest_dir, audio_file, youtube_url, spotify_url)

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
```

to:

```python
def _run_transcription_pipeline(audio_path: str, title: str, dest_dir: Path) -> None:
    """The CPU-bound half of /transcribe: piano transcription, beat
    detection, notation, and MusicXML export. Called via run_in_threadpool
    from the transcribe() route handler so a long transcription runs on a
    worker thread instead of blocking the event loop (and therefore every
    other concurrent request) for its full duration."""
    with job_slot(blocking=False):
        transcription = transcribe_piano_audio_to_notes(audio_path)
        notes = transcription.notes
        if not notes:
            raise HTTPException(status_code=422, detail="No pitched content detected")

        beat_map = detect_beat_map(audio_path)

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


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio_file: Optional[UploadFile] = File(None),
    youtube_url: Optional[str] = Form(None),
    spotify_url: Optional[str] = Form(None),
) -> TranscribeResponse:
    song_id = new_song_id()
    dest_dir: Optional[Path] = None

    try:
        dest_dir = song_dir(song_id)
        ingested = await _ingest_and_validate_duration(dest_dir, audio_file, youtube_url, spotify_url)

        title = ingested.title
        try:
            await run_in_threadpool(_run_transcription_pipeline, str(ingested.path), title, dest_dir)
        except NoJobSlotAvailable as exc:
            logger.warning("transcribe rejected for song_id=%s: %s", song_id, exc)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
```

(The rest of `transcribe` — `write_metadata`/`evict_oldest_songs`, the `except HTTPException`/`except Exception` cleanup blocks, and the final `return TranscribeResponse(...)` — is unchanged. `HTTPException` raised inside `_run_transcription_pipeline`, which runs on a worker thread via `run_in_threadpool`, propagates back through `await run_in_threadpool(...)` as a normal Python exception — Starlette's `run_in_threadpool` re-raises exceptions from the thread — so the existing outer `except HTTPException:`/`except Exception:` blocks in `transcribe()` catch it exactly as before. No change needed there.)

- [ ] **Step 4: Run it, verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k offloads_its_pipeline -v`
Expected: PASS — `/health` responds in well under 1 second even while the mocked transcription is still "running."

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS, zero failures (in particular, every other existing `/transcribe` test must still pass unchanged — the API contract didn't change).

- [ ] **Step 6: Commit**

```bash
cd /Users/knguyen/VSC/Synthony
git add backend/app/main.py backend/tests/test_api.py
git commit -m "$(cat <<'EOF'
fix: run /transcribe's pipeline on a worker thread, not the event loop

/transcribe's entire CPU-bound pipeline (piano transcription, beat
detection, notation, export) ran synchronously inside the async route
handler with no await anywhere in it, so it blocked the single event
loop thread for its full duration -- every other concurrent request,
including an unrelated /health call, had to wait behind it. Extracted
the pipeline into a plain function and offload it via Starlette's
run_in_threadpool. No API or behavior change -- /transcribe is still a
single blocking request/response from the client's perspective, it just
no longer blocks *other* requests while it runs.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Missing failure-path test for `run_arrange_pipeline`'s cleanup

**Files:**
- Modify: `backend/tests/test_arrange_pipeline.py`

**Interfaces:**
- Consumes: `run_arrange_pipeline`, `create_job`, `get_job`, `Stems` (already imported in this file).
- Produces: no production code change — this task only adds test coverage for existing, already-correct behavior.

**Context:** `run_arrange_pipeline`'s two `except` blocks already call `shutil.rmtree(dest_dir, ignore_errors=True)` on any failure (confirmed correct during the production-readiness pass's Task 1 review) — but no test actually exercises this path. The final whole-branch review flagged this as an untested gap: "nothing would catch a future refactor that drops it."

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_arrange_pipeline.py`, right after `test_run_arrange_pipeline_deletes_the_stems_directory_after_success` (the success-path test this one mirrors):

```python
def test_run_arrange_pipeline_deletes_the_whole_dest_dir_on_failure(tmp_path, monkeypatch):
    """Mirrors the success-path stems-cleanup test above: run_arrange_
    pipeline's except blocks already delete the ENTIRE dest_dir (not just
    stems/) on any failure -- this was previously unguarded by a test, so
    a future refactor could silently drop it without anything catching
    the regression."""
    import app.arrange_pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=tmp_path / "stems" / "vocals.wav", drums=tmp_path / "stems" / "drums.wav",
            bass=tmp_path / "stems" / "bass.wav", other=tmp_path / "stems" / "other.wav",
        ),
    )

    def _boom(audio_path):
        raise RuntimeError("simulated pipeline failure")

    monkeypatch.setattr(pipeline_module, "extract_melody_notes", _boom)

    job_id = create_job()
    run_arrange_pipeline(
        job_id=job_id, audio_path="fake.wav", title="Song",
        source_type="upload", source_url=None, song_id="fake-song-id",
        dest_dir=tmp_path,
    )

    assert get_job(job_id).status == "failed"
    assert not tmp_path.exists()
```

- [ ] **Step 2: Run it, verify it currently passes (confirming the pre-existing behavior this test locks in)**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -k deletes_the_whole_dest_dir_on_failure -v`
Expected: PASS immediately — this task adds coverage for already-correct behavior, so there's no RED step here (unlike a normal bug fix, there's nothing to make pass; the point is locking in existing correct behavior against future regression). If it unexpectedly FAILS, that's a real bug in the existing failure-path cleanup — stop and report it rather than adjusting the test to match broken behavior.

- [ ] **Step 3: Run the full backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS, zero failures.

- [ ] **Step 4: Commit**

```bash
cd /Users/knguyen/VSC/Synthony
git add backend/tests/test_arrange_pipeline.py
git commit -m "$(cat <<'EOF'
test: cover run_arrange_pipeline's failure-path dest_dir cleanup

The except blocks' shutil.rmtree(dest_dir, ...) on failure was already
correct (confirmed during the production-readiness pass) but had no
test locking it in, unlike the success-path stems cleanup right above
it in this file. Mirrors that test's structure for the failure case.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Small backlog batch (test isolation, logger restore, setup.sh, /health schema)

**Files:**
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/setup.sh`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces: no production behavior change from any of these four sub-items — test isolation, test robustness, script robustness, and an API schema annotation that doesn't change the actual JSON shape returned.

This task bundles four small, independent, same-shape fixes — each is a one-to-few-line change with no design ambiguity, all parked as Minor findings from the production-readiness pass's final review.

- [ ] **Step 1: Redirect `LOG_DIR` to an isolated test directory**

**Problem:** every test run currently writes to the real `backend/logs/app.log` (any test importing `app.main`, and in particular `test_api.py`'s `importlib.reload(main_module)` test, triggers `configure_logging()` against the real `LOG_DIR`). This pollutes the one file meant to be a durable crash-diagnosis trail with test noise. `STORAGE_ROOT` already has exactly this isolation — mirror it.

In `backend/tests/conftest.py`, change:

```python
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pretty_midi
import pytest
from scipy.io import wavfile

import app.storage as storage_module

_FLUIDSYNTH_SOUNDFONT = Path(pretty_midi.__file__).parent / "TimGM6mb.sf2"

# Redirect STORAGE_ROOT to an isolated, session-scoped temp directory *before*
# any test module (and, critically, app.main — which mounts a StaticFiles
# directory and mkdir()s STORAGE_ROOT at import time) gets imported. conftest.py
# is loaded by pytest before it collects/imports the test modules in this
# directory, so this assignment is visible to every later `from app.storage
# import STORAGE_ROOT` and to app.main's module-level use of it.
#
# This is what makes the test suite safe to run against a real, populated
# backend/storage/ directory: tests never touch the real STORAGE_ROOT at all.
_TEST_STORAGE_ROOT = Path(tempfile.mkdtemp(prefix="synthony-test-storage-"))
storage_module.STORAGE_ROOT = _TEST_STORAGE_ROOT
```

to:

```python
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pretty_midi
import pytest
from scipy.io import wavfile

import app.logging_config as logging_config_module
import app.storage as storage_module

_FLUIDSYNTH_SOUNDFONT = Path(pretty_midi.__file__).parent / "TimGM6mb.sf2"

# Redirect STORAGE_ROOT to an isolated, session-scoped temp directory *before*
# any test module (and, critically, app.main — which mounts a StaticFiles
# directory and mkdir()s STORAGE_ROOT at import time) gets imported. conftest.py
# is loaded by pytest before it collects/imports the test modules in this
# directory, so this assignment is visible to every later `from app.storage
# import STORAGE_ROOT` and to app.main's module-level use of it.
#
# This is what makes the test suite safe to run against a real, populated
# backend/storage/ directory: tests never touch the real STORAGE_ROOT at all.
_TEST_STORAGE_ROOT = Path(tempfile.mkdtemp(prefix="synthony-test-storage-"))
storage_module.STORAGE_ROOT = _TEST_STORAGE_ROOT

# Same isolation, same reasoning, for the rotating file handler's log
# directory: app.main's module-level configure_logging() call (and any
# test that reloads it) would otherwise write into the real
# backend/logs/app.log, polluting the one file meant to be a durable
# crash-diagnosis trail with test noise. Individual tests in
# test_logging_config.py further monkeypatch LOG_DIR per-test (overriding
# this default) to assert on rotation/fallback behavior in isolation.
_TEST_LOG_DIR = Path(tempfile.mkdtemp(prefix="synthony-test-logs-"))
logging_config_module.LOG_DIR = _TEST_LOG_DIR
```

- [ ] **Step 2: Verify no test regression**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_logging_config.py tests/test_api.py -v`
Expected: PASS, all tests — in particular the existing rotating-file tests in `test_logging_config.py` (which monkeypatch `LOG_DIR` per-test already) and `test_api.py`'s reload-based startup-warning test.

- [ ] **Step 3: Confirm the real log file is untouched by a test run**

Run: `cd backend && ls -la logs/app.log 2>&1; ./.venv/bin/python -m pytest -q >/dev/null 2>&1; ls -la logs/app.log 2>&1`
Expected: the file's mtime (if it exists at all) is unchanged before and after the test run — confirming tests no longer write to it. (If `backend/logs/app.log` doesn't exist yet on this machine because the server has never been run, both `ls` calls will just report "No such file" — that's fine, it equally confirms the test run didn't create it.)

- [ ] **Step 4: Add a logger-restore fixture to the startup-warning test**

**Problem:** `test_logs_a_warning_at_startup_when_ffmpeg_is_missing` calls `importlib.reload(main_module)`, which re-runs `configure_logging()` — `logging.basicConfig(force=True)` replaces the root logger's handlers and level for the rest of the test session. `test_logging_config.py` already has a dedicated fixture solving exactly this problem for its own tests; this test in `test_api.py` never got one.

`test_api.py` currently starts with:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_returns_ok():
```

Change it to:

```python
import logging

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture
def _restore_root_logger_state():
    """Same purpose as test_logging_config.py's fixture of the same name:
    importlib.reload(main_module) (used by the startup-warning test below)
    re-runs configure_logging(), which calls
    logging.basicConfig(force=True) and permanently replaces the root
    logger's level and handlers for the rest of the pytest session
    otherwise."""
    root = logging.getLogger()
    original_level = root.level
    original_handlers = list(root.handlers)
    yield
    root.level = original_level
    root.handlers = original_handlers


def test_health_check_returns_ok():
```

(`test_api.py` also has a second, pre-existing `import logging` / `import pytest` further down the file, right before `test_transcribe_unexpected_failure_logs_the_exception` — that one is unrelated to this change and harmless to leave as-is; don't remove it.)

Then change the test's signature from:

```python
def test_logs_a_warning_at_startup_when_ffmpeg_is_missing(monkeypatch):
```

to:

```python
def test_logs_a_warning_at_startup_when_ffmpeg_is_missing(monkeypatch, _restore_root_logger_state):
```

(The test body is otherwise unchanged — it already does `import logging` locally inside itself, which is now redundant with the new top-level import but harmless; leave it as-is rather than editing unrelated lines.)

- [ ] **Step 5: Run it, verify it still passes and no longer leaks state**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k logs_a_warning_at_startup -v`
Expected: PASS.

- [ ] **Step 6: `setup.sh` should rebuild cleanly, not silently reuse a stale `.venv`**

In `backend/setup.sh`, change:

```bash
python3.11 -m venv .venv
```

to:

```bash
python3.11 -m venv .venv --clear
```

(`--clear` deletes and recreates the target directory if it already exists, guaranteeing a known-good environment every run — matching the script's own stated purpose of preventing exactly the class of obscure failure a stale or half-broken `.venv` would cause.)

- [ ] **Step 7: Verify the script's syntax**

Run: `bash -n backend/setup.sh`
Expected: no output, exit code 0. (Do not actually run the script — same reasoning as when it was first created: it would build a redundant multi-GB venv.)

- [ ] **Step 8: Add a Pydantic response model to `/health`**

In `backend/app/main.py`, change:

```python
class ArrangeSubmitResponse(BaseModel):
    job_id: str
    status: str
```

to:

```python
class ArrangeSubmitResponse(BaseModel):
    job_id: str
    status: str


class HealthResponse(BaseModel):
    status: str
    ffmpeg_available: bool
    piano_model_downloaded: bool
```

Then change:

```python
@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "piano_model_downloaded": piano_checkpoint_downloaded(),
    }
```

to:

```python
@app.get("/health", response_model=HealthResponse)
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "piano_model_downloaded": piano_checkpoint_downloaded(),
    }
```

- [ ] **Step 9: Run the existing `/health` tests, verify they still pass unchanged**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k health_check -v`
Expected: PASS — the three existing `/health` tests already assert on the exact JSON shape FastAPI will now validate against `HealthResponse`; no test changes needed since the response model's fields exactly match what the endpoint already returns.

- [ ] **Step 10: Run the full backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS, zero failures.

- [ ] **Step 11: Commit**

```bash
cd /Users/knguyen/VSC/Synthony
git add backend/tests/conftest.py backend/tests/test_api.py backend/setup.sh backend/app/main.py
git commit -m "$(cat <<'EOF'
fix: small backlog batch from the production-readiness pass's final review

- tests: redirect LOG_DIR to an isolated directory (mirrors the existing
  STORAGE_ROOT redirect) so test runs stop writing into the real
  backend/logs/app.log
- tests: give the startup-warning test its own logger-restore fixture,
  matching test_logging_config.py's existing one, so its
  importlib.reload() doesn't leak root-logger state for the rest of the
  session
- setup.sh: rebuild the venv with --clear instead of silently reusing
  (and potentially upgrading-in-place) a stale or half-broken one
- /health: use a Pydantic HealthResponse model like every sibling
  endpoint, instead of a bare dict -- gets real OpenAPI schema
  documentation for free, no response-shape change

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

## Deferred (not in scope here)

- The "install recipe lives in 4 places" observation (README, `setup.sh`, CI, Dockerfile) from the final review — informational only, no concrete fix proposed; left as a known fact, not a task.
- Big Rock's tempo complaint, the instrumental-arrangement-quality revisit, and broadening past pop/rock — each needs its own investigation/brainstorm-and-spec cycle, sequenced after this plan per the user's own ordering.
