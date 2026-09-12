# Production-Readiness Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden Synthony for reliable local, single-user, single-machine
operation: clean up dead disk artifacts, make startup/health issues
visible instead of silent, and make backend setup a one-command affair —
then audit for anything else that would annoy someone actually running it.

**Architecture:** Four small, independent, surgical changes to existing
code (no new subsystems, no new services): a cleanup call added to the
end of the existing arrange pipeline, two new fields added to the
existing `/health` endpoint plus a startup-time log line, a second
logging handler added to the existing logging setup, and a new shell
script that mechanizes an already-documented manual setup sequence. A
final task runs a verification sweep across both the backend and
frontend.

**Tech Stack:** Python 3.11/FastAPI (backend), pytest, stdlib `logging`/`logging.handlers`, bash.

**Spec:** `docs/superpowers/specs/2026-09-12-production-readiness-pass-design.md`

## Global Constraints

- TDD is non-negotiable for backend Python work — write the failing test first.
- Run the full backend suite (`cd backend && ./.venv/bin/python -m pytest -v`) before any backend commit.
- Self-hosted, single-user, local-only scope: none of these changes should add authentication, rate limiting, multi-tenant isolation, or public/always-on deployment — that's explicitly out of scope (confirmed with the user during brainstorming).
- No size-based storage eviction cap — the existing count-based `evict_oldest_songs()` (`MAX_STORED_SONGS = 100`) stays as-is; Task 1 below removes the dead weight that made it insufficient, it doesn't replace it.

---

## File Structure

- **Modify:** `backend/app/arrange_pipeline.py` — delete `dest_dir/"stems"` after a successful run (Task 1).
- **Modify:** `backend/app/transcription/audio_to_midi.py` — add a public `piano_checkpoint_downloaded()` helper, reused by both `/health` and the existing `_ensure_piano_checkpoint()` (Task 2).
- **Modify:** `backend/app/main.py` — extend `GET /health` with `ffmpeg_available`/`piano_model_downloaded`; log a startup warning if `ffmpeg` is missing (Task 2).
- **Modify:** `backend/app/logging_config.py` — add a rotating file handler alongside the existing stdout handler (Task 3).
- **Modify:** `.gitignore` — ignore the new `backend/logs/` directory (Task 3).
- **Create:** `backend/setup.sh` — mechanizes the backend venv setup sequence already documented in `README.md` (Task 4).
- **Modify:** `README.md` — point at `backend/setup.sh` as the primary setup path, keep the manual steps as documented fallback (Task 4).
- **Test:** `backend/tests/test_arrange_pipeline.py`, `backend/tests/test_audio_to_midi.py`, `backend/tests/test_api.py`, `backend/tests/test_logging_config.py`.

No new backend modules, no new frontend changes.

---

### Task 1: Delete dead stem files after a successful arrange

**Files:**
- Modify: `backend/app/arrange_pipeline.py`
- Test: `backend/tests/test_arrange_pipeline.py`

**Interfaces:**
- Consumes: `shutil.rmtree` (already imported in `arrange_pipeline.py`).
- Produces: no signature/behavior change to `run_arrange_pipeline` — same params, same return (`None`), same exceptions. Only removes files as a side effect after success.

**Context:** `run_arrange_pipeline`'s two `except` blocks already call
`shutil.rmtree(dest_dir, ignore_errors=True)` on any failure — that
already deletes stems along with everything else, so failure paths need
no change. The gap is the *success* path: `dest_dir/"stems"/` (the four
Demucs stem WAVs, plus a mixed `harmony.wav`) is never touched once the
three MusicXML tiers are exported, even though nothing reads those files
again.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_arrange_pipeline.py`, right after
`test_run_arrange_pipeline_fails_cleanly_when_slot_wait_times_out` (this
file already imports `threading`, `time`, `run_arrange_pipeline`,
`create_job`, `get_job`, `Stems`, `BeatMap`, and `NoteEvent` above that
point — reuse them, don't re-import):

```python
def test_run_arrange_pipeline_deletes_the_stems_directory_after_success(tmp_path, monkeypatch):
    """Demucs's separated stem WAVs (and the mixed harmony.wav) are never
    read again once all three MusicXML tiers are exported -- they must
    not linger on disk forever. Real separate_stems() is mocked here (as
    in the job-slot tests above), so this test pre-creates a stems/
    directory with a dummy file to stand in for what the real call would
    have left behind, and asserts it's gone once the pipeline finishes
    successfully."""
    import app.arrange_pipeline as pipeline_module

    (tmp_path / "stems").mkdir()
    (tmp_path / "stems" / "vocals.wav").write_bytes(b"fake")

    fake_notes = [NoteEvent(start=float(i), end=float(i) + 0.5, pitch=72) for i in range(10)]
    fake_lh_notes = [NoteEvent(start=0.0, end=0.5, pitch=48)]
    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=tmp_path / "stems" / "vocals.wav", drums=tmp_path / "stems" / "drums.wav",
            bass=tmp_path / "stems" / "bass.wav", other=tmp_path / "stems" / "other.wav",
        ),
    )
    monkeypatch.setattr(pipeline_module, "mix_wav_files", lambda a, b, dest: dest)
    monkeypatch.setattr(pipeline_module, "extract_melody_notes", lambda audio_path: fake_notes)
    monkeypatch.setattr(pipeline_module, "extract_lh_notes", lambda audio_path: fake_lh_notes)
    monkeypatch.setattr(pipeline_module, "detect_key_and_tempo", lambda audio_path: ((0, "major"), 0.5))
    monkeypatch.setattr(pipeline_module, "detect_beat_map", lambda audio_path: BeatMap.constant(0.5))

    job_id = create_job()
    run_arrange_pipeline(
        job_id=job_id, audio_path="fake.wav", title="Song",
        source_type="upload", source_url=None, song_id="fake-song-id",
        dest_dir=tmp_path,
    )

    assert get_job(job_id).status == "done"
    assert not (tmp_path / "stems").exists()
    assert (tmp_path / "hard.musicxml").exists()
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -k deletes_the_stems_directory -v`
Expected: FAIL — `assert not (tmp_path / "stems").exists()` fails because nothing deletes it yet.

- [ ] **Step 3: Implement**

In `backend/app/arrange_pipeline.py`, in `run_arrange_pipeline`, change:

```python
            write_metadata(song_id, title=title, source_type=source_type, source_url=source_url, pipeline="arrange")
            evict_oldest_songs()

        set_result(job_id, {"song_id": song_id, "title": title, "difficulties": difficulties})
```

to:

```python
            shutil.rmtree(dest_dir / "stems", ignore_errors=True)
            write_metadata(song_id, title=title, source_type=source_type, source_url=source_url, pipeline="arrange")
            evict_oldest_songs()

        set_result(job_id, {"song_id": song_id, "title": title, "difficulties": difficulties})
```

- [ ] **Step 4: Run it, verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -k deletes_the_stems_directory -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS, zero failures.

- [ ] **Step 6: Commit**

```bash
cd /Users/knguyen/VSC/Synthony
git add backend/app/arrange_pipeline.py backend/tests/test_arrange_pipeline.py
git commit -m "$(cat <<'EOF'
fix: delete Demucs stem files after a successful arrange

dest_dir/stems/ (the 4 separated WAVs plus a mixed harmony.wav) was
never cleaned up once all three MusicXML tiers were exported, even
though nothing reads those files again -- across the existing 100-song
storage cap this was potentially several GB of dead weight the
count-based eviction doesn't touch mid-song. Failure paths already
delete the whole song directory via the existing except blocks; this
was the one gap, on the success path.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Health check reports ffmpeg/model status; startup warning

**Files:**
- Modify: `backend/app/transcription/audio_to_midi.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_audio_to_midi.py`, `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `shutil.which` (stdlib, `shutil` already imported in `main.py`).
- Produces: `piano_checkpoint_downloaded() -> bool`, a new public function
  in `app.transcription.audio_to_midi`, importable as
  `from app.transcription.audio_to_midi import piano_checkpoint_downloaded`.
  `GET /health` now returns `{"status": str, "ffmpeg_available": bool, "piano_model_downloaded": bool}`
  instead of just `{"status": str}` — a response-shape change any future
  caller of `/health` must expect.

- [ ] **Step 1: Write the failing test for `piano_checkpoint_downloaded`**

Add to `backend/tests/test_audio_to_midi.py`:

```python
def test_piano_checkpoint_downloaded_true_when_file_exists_and_is_large_enough(tmp_path, monkeypatch):
    import app.transcription.audio_to_midi as audio_to_midi_module

    # Patch the size threshold down too -- writing a real
    # _MIN_CHECKPOINT_SIZE_BYTES-sized (160MB) file just to satisfy this
    # check would make the test slow and disk-heavy for no reason.
    fake_checkpoint = tmp_path / "checkpoint.pth"
    fake_checkpoint.write_bytes(b"x" * 100)
    monkeypatch.setattr(audio_to_midi_module, "_PIANO_CHECKPOINT_PATH", fake_checkpoint)
    monkeypatch.setattr(audio_to_midi_module, "_MIN_CHECKPOINT_SIZE_BYTES", 100)

    assert audio_to_midi_module.piano_checkpoint_downloaded() is True


def test_piano_checkpoint_downloaded_false_when_file_is_missing(tmp_path, monkeypatch):
    import app.transcription.audio_to_midi as audio_to_midi_module

    monkeypatch.setattr(audio_to_midi_module, "_PIANO_CHECKPOINT_PATH", tmp_path / "does-not-exist.pth")

    assert audio_to_midi_module.piano_checkpoint_downloaded() is False


def test_piano_checkpoint_downloaded_false_when_file_is_truncated(tmp_path, monkeypatch):
    import app.transcription.audio_to_midi as audio_to_midi_module

    truncated = tmp_path / "checkpoint.pth"
    truncated.write_bytes(b"x" * 10)  # far below the (patched) threshold
    monkeypatch.setattr(audio_to_midi_module, "_PIANO_CHECKPOINT_PATH", truncated)
    monkeypatch.setattr(audio_to_midi_module, "_MIN_CHECKPOINT_SIZE_BYTES", 100)

    assert audio_to_midi_module.piano_checkpoint_downloaded() is False
```

- [ ] **Step 2: Run them, verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_audio_to_midi.py -k piano_checkpoint_downloaded -v`
Expected: FAIL — `AttributeError: module 'app.transcription.audio_to_midi' has no attribute 'piano_checkpoint_downloaded'`.

- [ ] **Step 3: Implement `piano_checkpoint_downloaded`**

In `backend/app/transcription/audio_to_midi.py`, change:

```python
def _ensure_piano_checkpoint() -> Path:
    if not _PIANO_CHECKPOINT_PATH.exists() or _PIANO_CHECKPOINT_PATH.stat().st_size < _MIN_CHECKPOINT_SIZE_BYTES:
        _PIANO_CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(_PIANO_CHECKPOINT_URL, _PIANO_CHECKPOINT_PATH)
    return _PIANO_CHECKPOINT_PATH
```

to:

```python
def piano_checkpoint_downloaded() -> bool:
    """True if the piano transcription model's checkpoint has already
    been downloaded (and isn't a truncated/corrupt partial download) --
    used by /health to report this without triggering the download."""
    return (
        _PIANO_CHECKPOINT_PATH.exists()
        and _PIANO_CHECKPOINT_PATH.stat().st_size >= _MIN_CHECKPOINT_SIZE_BYTES
    )


def _ensure_piano_checkpoint() -> Path:
    if not piano_checkpoint_downloaded():
        _PIANO_CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(_PIANO_CHECKPOINT_URL, _PIANO_CHECKPOINT_PATH)
    return _PIANO_CHECKPOINT_PATH
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_audio_to_midi.py -k piano_checkpoint_downloaded -v`
Expected: PASS.

- [ ] **Step 5: Write the failing tests for `/health`**

In `backend/tests/test_api.py`, change the existing:

```python
def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

to:

```python
def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_check_reports_ffmpeg_and_piano_model_status_when_both_present(monkeypatch):
    import shutil as shutil_module
    import app.main as main_module

    monkeypatch.setattr(shutil_module, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(main_module, "piano_checkpoint_downloaded", lambda: True)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ffmpeg_available": True,
        "piano_model_downloaded": True,
    }


def test_health_check_reports_missing_ffmpeg_and_undownloaded_model(monkeypatch):
    import shutil as shutil_module
    import app.main as main_module

    monkeypatch.setattr(shutil_module, "which", lambda name: None)
    monkeypatch.setattr(main_module, "piano_checkpoint_downloaded", lambda: False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ffmpeg_available": False,
        "piano_model_downloaded": False,
    }
```

(`shutil` is patched at the real module it lives in — `import shutil`
is a single shared module object, so patching `shutil.which` this way
also affects `app.main`'s own `shutil.which(...)` call, since it's the
same object. `piano_checkpoint_downloaded` is patched directly on
`app.main` since that's where `main.py` imports it into its own
namespace.)

- [ ] **Step 6: Run them, verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k health_check -v`
Expected: the two new tests FAIL (`KeyError`/`AssertionError` — the extra fields don't exist yet); the loosened `test_health_check_returns_ok` still passes.

- [ ] **Step 7: Implement `/health` and the startup warning**

In `backend/app/main.py`, change:

```python
from app.transcription.audio_to_midi import transcribe_piano_audio_to_notes
```

to:

```python
from app.transcription.audio_to_midi import piano_checkpoint_downloaded, transcribe_piano_audio_to_notes
```

Then change:

```python
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

to:

```python
@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "piano_model_downloaded": piano_checkpoint_downloaded(),
    }
```

Then add a startup-time warning. Change:

```python
configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI()
```

to:

```python
configure_logging()
logger = logging.getLogger(__name__)

if shutil.which("ffmpeg") is None:
    logger.warning(
        "ffmpeg not found on PATH -- YouTube/Spotify-link ingestion will fail "
        "(file upload is unaffected)"
    )

app = FastAPI()
```

- [ ] **Step 8: Run the tests, verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k health_check -v`
Expected: PASS, all three.

- [ ] **Step 9: Write the failing test for the startup warning**

Add to `backend/tests/test_api.py`:

```python
def test_logs_a_warning_at_startup_when_ffmpeg_is_missing(monkeypatch, caplog):
    import importlib
    import logging
    import shutil as shutil_module
    import app.main as main_module

    monkeypatch.setattr(shutil_module, "which", lambda name: None)

    with caplog.at_level(logging.WARNING, logger="app.main"):
        importlib.reload(main_module)

    assert any("ffmpeg" in record.message.lower() for record in caplog.records)
```

(Reloading `app.main` re-runs its module-level code, including the new
startup check. This doesn't affect this file's own module-level `client
= TestClient(app)` — that name was bound once, at import time, to the
original `app` object, which is unaffected by the reload. Run this test
last in the file's health-check group since it's the most invasive of
the three.)

- [ ] **Step 10: Run it, verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k logs_a_warning_at_startup -v`
Expected: FAIL — no warning logged yet.

- [ ] **Step 11: Run it, verify it passes**

(No new implementation needed — Step 7 already added the startup
warning.) Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k logs_a_warning_at_startup -v`
Expected: PASS.

- [ ] **Step 12: Run the full backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS, zero failures.

- [ ] **Step 13: Commit**

```bash
cd /Users/knguyen/VSC/Synthony
git add backend/app/transcription/audio_to_midi.py backend/app/main.py backend/tests/test_audio_to_midi.py backend/tests/test_api.py
git commit -m "$(cat <<'EOF'
feat: report ffmpeg/piano-model status from /health, warn at startup

/health previously always returned {"status": "ok"} unconditionally --
no way to tell, right after starting the server, whether ffmpeg is on
PATH (needed for YouTube/Spotify ingestion) or whether the piano
transcription model's ~170MB checkpoint has been downloaded yet. Also
logs a startup-time warning when ffmpeg is missing, so it's visible in
the terminal at boot instead of only surfacing when a YouTube/Spotify
request eventually fails deep in ingestion.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Rotating file logging

**Files:**
- Modify: `backend/app/logging_config.py`
- Modify: `.gitignore`
- Test: `backend/tests/test_logging_config.py`

**Interfaces:**
- Consumes: stdlib `logging.handlers.RotatingFileHandler`.
- Produces: `configure_logging()` keeps its existing signature (no
  params, returns `None`) — behavior gains a second handler, callers
  don't change. Adds a new module-level `LOG_DIR` constant in
  `app.logging_config`, monkeypatchable by tests.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_logging_config.py` (this file already has an
autouse `_restore_root_logger_state` fixture that undoes
`logging.basicConfig(force=True)`'s effects after each test — it applies
automatically here too):

```python
def test_configure_logging_writes_to_a_rotating_file_in_addition_to_stdout(tmp_path, monkeypatch):
    import app.logging_config as logging_config_module

    monkeypatch.setattr(logging_config_module, "LOG_DIR", tmp_path / "logs")

    configure_logging()
    logging.getLogger("test-logger").info("hello from the test")

    log_file = tmp_path / "logs" / "app.log"
    assert log_file.exists()
    assert "hello from the test" in log_file.read_text()


def test_configure_logging_file_handler_has_rotation_configured(tmp_path, monkeypatch):
    import logging.handlers
    import app.logging_config as logging_config_module

    monkeypatch.setattr(logging_config_module, "LOG_DIR", tmp_path / "logs")

    configure_logging()

    file_handlers = [
        h for h in logging.getLogger().handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert len(file_handlers) == 1
    assert file_handlers[0].maxBytes == 5 * 1024 * 1024
    assert file_handlers[0].backupCount == 3
```

- [ ] **Step 2: Run them, verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_logging_config.py -k rotating -v`
Expected: FAIL — `AttributeError: module 'app.logging_config' has no attribute 'LOG_DIR'` (or the log file never gets created).

- [ ] **Step 3: Implement**

Replace the full contents of `backend/app/logging_config.py`:

```python
import logging
import logging.handlers
import os
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def configure_logging() -> None:
    """Configure the root logger once at process startup. Level is
    overridable via the LOG_LEVEL env var (e.g. LOG_LEVEL=DEBUG) for local
    debugging. Uses force=True so calling this more than once (e.g. from a
    test that wants a fresh level) actually takes effect, instead of
    logging.basicConfig's normal "no-op after the first call" behavior.

    Logs go to both stdout (as before) and a rotating file under
    backend/logs/, so there's a persisted trail to check after a crash if
    the server is ever run backgrounded rather than in a foreground
    terminal."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = logging.getLevelNamesMapping().get(level_name, logging.INFO)
    log_format = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(logging.Formatter(log_format))

    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[logging.StreamHandler(), file_handler],
        force=True,
    )
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_logging_config.py -v`
Expected: PASS, all four (the two pre-existing plus the two new ones).

- [ ] **Step 5: Ignore the new log directory**

In `.gitignore`, change:

```
# Python
__pycache__/
*.pyc
.venv
backend/storage/
```

to:

```
# Python
__pycache__/
*.pyc
.venv
backend/storage/
backend/logs/
```

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS, zero failures.

- [ ] **Step 7: Commit**

```bash
cd /Users/knguyen/VSC/Synthony
git add backend/app/logging_config.py backend/tests/test_logging_config.py .gitignore
git commit -m "$(cat <<'EOF'
feat: persist logs to a rotating file, not just stdout

configure_logging() previously only logged to stdout via
logging.basicConfig -- fine while watching a foreground terminal, but
nothing survived if the server was ever run backgrounded and crashed.
Adds a RotatingFileHandler (5MB x 3 backups) writing to backend/logs/,
alongside the existing stream handler.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `backend/setup.sh`

**Files:**
- Create: `backend/setup.sh`
- Modify: `README.md`

**Interfaces:**
- Produces: an executable shell script at `backend/setup.sh`, no
  parameters, run from any working directory (it `cd`s to its own
  location first). Idempotent to run more than once — `python3.11 -m
  venv .venv` is a no-op if `.venv` already exists.

- [ ] **Step 1: Create the script**

Write `backend/setup.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3.11 >/dev/null 2>&1; then
  echo "python3.11 not found. Install it first (e.g. 'brew install python@3.11')." >&2
  exit 1
fi

python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# madmom (unmaintained since ~2022) needs numpy/Cython/scipy/mido already
# present to build from its sdist, and must be installed with build
# isolation off -- see the comments on madmom/numpy/setuptools in
# requirements.txt for why.
pip install "numpy>=1.26.4,<2.0" scipy cython mido "setuptools<81"
pip install --no-build-isolation -r requirements.txt

echo ""
echo "Backend environment ready. Activate it with:"
echo "    source backend/.venv/bin/activate"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x backend/setup.sh`

- [ ] **Step 3: Verify it against the README's documented sequence**

This script has no automated test (it's an environment-setup script, not
application code — the existing `.venv` was already built by running
this exact command sequence manually, which is what originally verified
it works). Instead, verify by inspection: run `bash -n backend/setup.sh`
to check it parses with no syntax errors, then diff its commands
line-by-line against the "Backend" section of `README.md` (before Step 4
changes it) to confirm every command matches exactly, in the same order,
with the same flags.

Run: `bash -n backend/setup.sh`
Expected: no output, exit code 0.

- [ ] **Step 4: Update the README to point at the script**

In `README.md`, change:

```
Requires Python 3.11 (`brew install python@3.11` if you don't have it — newer
music21 needs 3.10+, and macOS/Homebrew no longer ship 3.9).

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
# madmom (unmaintained since ~2022) needs numpy/Cython/scipy/mido already present
# to build from its sdist, and must be installed with build isolation off — see
# the comments on madmom/numpy/setuptools in requirements.txt for why.
pip install "numpy>=1.26.4,<2.0" scipy cython mido "setuptools<81"
pip install --no-build-isolation -r requirements.txt
uvicorn app.main:app --reload
```
```

to:

```
Requires Python 3.11 (`brew install python@3.11` if you don't have it — newer
music21 needs 3.10+, and macOS/Homebrew no longer ship 3.9).

```bash
cd backend
./setup.sh
source .venv/bin/activate
uvicorn app.main:app --reload
```

`setup.sh` runs the exact manual sequence below — shown here for
reference, or in case the script doesn't work unmodified on your
platform:

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
# madmom (unmaintained since ~2022) needs numpy/Cython/scipy/mido already present
# to build from its sdist, and must be installed with build isolation off — see
# the comments on madmom/numpy/setuptools in requirements.txt for why.
pip install "numpy>=1.26.4,<2.0" scipy cython mido "setuptools<81"
pip install --no-build-isolation -r requirements.txt
```
```

- [ ] **Step 5: Commit**

```bash
cd /Users/knguyen/VSC/Synthony
git add backend/setup.sh README.md
git commit -m "$(cat <<'EOF'
feat: add backend/setup.sh to mechanize the manual venv setup dance

Backend setup was five sequential manual steps, one of which (a pinned
numpy/scipy/cython/mido pre-install before madmom's --no-build-isolation
install) exists only because of a documented, easy-to-get-wrong build
quirk -- a copy-paste error here fails obscurely deep in pip install,
not with a clear message. setup.sh runs the exact same sequence as one
command, with set -euo pipefail so it stops cleanly on the first
failure. The manual steps stay in the README as documented fallback.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Closing audit sweep

**Files:** none pre-determined — this task's own findings decide what,
if anything, gets touched.

- [ ] **Step 1: Verify the frontend production build/preview path**

Run:
```bash
cd frontend
npm run build
npm run preview -- --port 4173 &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:4173
kill %1
```
Expected: `npm run build` completes with no errors; the `curl` line
prints `200`. If either fails, read the error output, fix the underlying
issue (not by weakening the build), and re-run this step until it
passes.

- [ ] **Step 2: Verify Docker still works end-to-end**

Run:
```bash
cd /Users/knguyen/VSC/Synthony
docker compose build
docker compose up -d
sleep 5
curl -s http://localhost:8000/health
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173
docker compose down
```
Expected: both builds succeed, the backend `/health` response includes
the new `ffmpeg_available`/`piano_model_downloaded` fields from Task 2
(confirming the Docker image actually has `ffmpeg` on `PATH` — it should,
per the existing Dockerfile), and the frontend responds `200`. If Docker
isn't installed/running in this environment, skip this step and say so
explicitly rather than silently treating it as passed.

- [ ] **Step 3: Re-verify the README against the actual current setup**

Read `README.md` top to bottom and compare each documented command
against the actual current codebase (env var names in
`backend/app/main.py`, script names in `frontend/package.json`, the
`backend/setup.sh` reference added in Task 4, the `/health` response
shape from Task 2). Fix any command, path, or claim that's gone stale.
If nothing is stale, say so explicitly rather than making a cosmetic
change to have something to commit.

- [ ] **Step 4: Spot-check frontend error-message clarity**

Read the user-facing error strings touched by the Tier 1 bug-fix pass
(`frontend/src/components/QrScanButton.tsx`,
`frontend/src/components/UploadForm.tsx`,
`frontend/src/components/DifficultyTabs.tsx`,
`frontend/src/components/ScoreViewer.tsx`,
`frontend/src/components/HistoryTab.tsx`) as if seeing them for the
first time with no engineering context. Flag (and fix, if small) any
message that's technically correct but wouldn't make sense to someone
who doesn't know what "OSMD" or "MusicXML" means.

- [ ] **Step 5: Run both full test suites**

Run:
```bash
cd backend && ./.venv/bin/python -m pytest -v
cd ../frontend && npm test
```
Expected: PASS, zero failures, for both.

- [ ] **Step 6: Commit, if anything changed**

```bash
cd /Users/knguyen/VSC/Synthony
git status
```
If Steps 1–4 produced any file changes, stage exactly those files and commit:
```bash
git add <changed files>
git commit -m "$(cat <<'EOF'
fix: closing audit sweep for the production-readiness pass

<one line per concrete finding fixed>

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
If nothing changed, skip this step — don't create an empty commit.

## Deferred (not in scope here)

- A size-based storage eviction cap (only the count-based `MAX_STORED_SONGS` cap exists) — not needed now that Task 1 removes the dead weight that made per-song footprint unpredictable; revisit only if disk usage becomes a real problem in practice.
- Public/always-on deployment, authentication, rate limiting, multi-tenant isolation — explicitly out of scope per the confirmed local-only, single-user scope.
- `/transcribe`'s synchronous, event-loop-blocking behavior — a separate, already-identified, lower-priority item tracked in `TAKEAWAYS.md`'s "What's next," not part of this pass.
