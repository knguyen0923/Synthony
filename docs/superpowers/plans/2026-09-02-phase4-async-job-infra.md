# Async Job Infra (Spec 2, Phase 4 — backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Phases 1-3 (stem separation, melody extraction, chord
recognition, the LH arrangement engine) into a real, working `POST
/arrange` + `GET /arrange/{job_id}` async job — the point where Spec 2
stops being independent building blocks and becomes an actual pipeline a
user can call.

**Architecture:** A new in-memory job store (`app/jobs.py`), a pipeline
orchestrator (`app/arrange_pipeline.py`) that calls the four existing
modules in sequence and writes MusicXML output through the **unchanged**
`build_grand_staff_score` / `export_musicxml` (exactly like `/transcribe`
does today), and two new FastAPI routes in `app/main.py` using FastAPI's
`BackgroundTasks` to run the pipeline after the `202` response is sent —
no new task-queue dependency (Celery/Redis) needed at this scale, matching
the rest of this codebase's "simplest thing that works for personal use"
philosophy (see `storage.py`'s in-memory history cap for precedent).

**Tech Stack:** Python, FastAPI `BackgroundTasks` (no new dependency).

**Spec:** `docs/superpowers/specs/2026-09-01-any-song-arrangement-design.md`
(see "API Contract", "Storage", "Phased Roadmap" → Phase 4, "Testing
Strategy" → API layer). This plan covers the backend half of Phase 4 only
— the frontend input-mode toggle and progress UI are a separate,
follow-up plan.

## Prerequisite: merge in Phase 1, 2, and 3 first

This plan's code imports from `app.arrangement` (Phase 3), `app.separation`
and `app.melody` (Phase 1), and `app.chords` (Phase 2). **Before starting
Task 1**, confirm your branch actually has all of them:

```bash
ls backend/app/arrangement backend/app/separation backend/app/melody backend/app/chords
```

If any directory is missing, merge in whichever of these branches you're
missing (they exist both locally and pushed to `origin`; merges should be
conflict-free since each touches disjoint files — verify with
`git status` after each merge, not just a clean exit code):

```bash
git merge origin/worktree-agent-ae0efcb439964d5f3 --no-edit  # Phase 1: separation + melody
git merge origin/worktree-agent-abfcd127b6e94a917 --no-edit  # Phase 2: chords (already includes Phase 3)
```

Run `cd backend && ./.venv/bin/python -m pytest -q` after merging to
confirm a clean baseline before starting Task 1.

## Global Constraints

- No new dependencies. `BackgroundTasks` is part of FastAPI (already a
  dependency); `numpy`/`scipy` (for `mix_wav_files`) are already present.
- Job storage is a simple in-memory dict, matching the spec's note that
  "in-memory vs. persisted... is left for the Phase 4 implementation
  plan" — this plan chooses in-memory, consistent with `storage.py`'s
  existing in-memory-cap philosophy for a personal-use app.
- `build_grand_staff_score`, `export_musicxml`, and the difficulty engine
  are reused **completely unchanged** — Phase 2 (of the spec's own
  numbering, not this plan's tasks) only replaces how RH/LH `Part`s are
  produced, never anything downstream of the grand-staff `Score`, per the
  spec's Architecture section.
- Error responses: a failed job's `GET` response is `200` with
  `{"status": "failed", "detail": "..."}`, never an HTTP error status —
  per the spec's "Error responses" section, since the failure is
  discovered asynchronously after the initial `202`.
- API-layer tests follow this codebase's established pattern
  (`backend/tests/test_api.py`): use `monkeypatch` to replace the slow
  pipeline-stage functions with fast fakes, rather than running real
  Demucs/Basic Pitch/librosa end-to-end in every test run.

---

## File Structure

- Modify: `backend/app/storage.py` (`write_metadata` gains a `pipeline`
  parameter)
- Modify: `backend/app/main.py` (`SongSummary` gains a `pipeline` field;
  later, the two new `/arrange` routes)
- Create: `backend/app/jobs.py`
- Create: `backend/app/arrange_pipeline.py`
- Create: `backend/tests/test_jobs.py`
- Create: `backend/tests/test_arrange_pipeline.py`
- Modify: `backend/tests/test_storage.py` (two new tests)
- Modify: `backend/tests/test_api.py` (new tests for `/arrange`)

## Task 1: `metadata.json` pipeline field

**Files:**
- Modify: `backend/app/storage.py`
- Modify: `backend/app/main.py` (just the `SongSummary` model in this
  task — the `/arrange` routes come in Task 4)
- Modify: `backend/tests/test_storage.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Modifies: `write_metadata(song_id: str, title: str, source_type: str, source_url: Optional[str], pipeline: str = "transcribe") -> None`
  in `app.storage` — existing call sites (in `/transcribe`) don't need to
  change, since the new parameter defaults to `"transcribe"`.
- Modifies: `SongSummary` in `app.main` — adds `pipeline: str = "transcribe"`
  (the default matters: old `metadata.json` files written before this
  change have no `"pipeline"` key at all, and would otherwise fail
  response validation when listed).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_storage.py` (after the existing
`test_write_metadata_writes_expected_json_fields` test):

```python
def test_write_metadata_defaults_pipeline_to_transcribe():
    song_id = new_song_id()
    song_dir(song_id)

    write_metadata(song_id, title="My Song", source_type="upload", source_url=None)

    metadata_path = STORAGE_ROOT / song_id / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    assert metadata["pipeline"] == "transcribe"


def test_write_metadata_records_arrange_pipeline_when_specified():
    song_id = new_song_id()
    song_dir(song_id)

    write_metadata(song_id, title="My Song", source_type="upload", source_url=None, pipeline="arrange")

    metadata_path = STORAGE_ROOT / song_id / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    assert metadata["pipeline"] == "arrange"
```

Add to `backend/tests/test_api.py` (after
`test_get_song_returns_the_same_shape_as_transcribe`):

```python
def test_songs_listing_includes_pipeline_field(synthetic_piano_wav):
    with open(synthetic_piano_wav, "rb") as f:
        response = client.post(
            "/transcribe",
            files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
        )
    song_id = response.json()["song_id"]

    listing = client.get("/songs").json()
    entry = next(s for s in listing if s["song_id"] == song_id)
    assert entry["pipeline"] == "transcribe"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_storage.py tests/test_api.py -v -k "pipeline"`
Expected: FAIL — `write_metadata()` raises `TypeError: write_metadata() got an unexpected keyword argument 'pipeline'`
for the storage tests, and `KeyError: 'pipeline'` for the API test.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/storage.py`, change the `write_metadata` signature and body:

```python
def write_metadata(song_id: str, title: str, source_type: str, source_url: Optional[str], pipeline: str = "transcribe") -> None:
    metadata = {
        "title": title,
        "source_type": source_type,
        "source_url": source_url,
        "pipeline": pipeline,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (song_dir(song_id) / "metadata.json").write_text(json.dumps(metadata, indent=2))
```

In `backend/app/main.py`, add a `pipeline` field to the `SongSummary`
model:

```python
class SongSummary(BaseModel):
    song_id: str
    title: str
    source_type: str
    source_url: Optional[str]
    pipeline: str = "transcribe"
    created_at: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_storage.py tests/test_api.py -v`
Expected: PASS — the full existing suite for both files, plus the 3 new
tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage.py backend/app/main.py backend/tests/test_storage.py backend/tests/test_api.py
git commit -m "feat: add pipeline field to song metadata"
```

## Task 2: In-memory job store

**Files:**
- Create: `backend/app/jobs.py`
- Test: `backend/tests/test_jobs.py`

**Interfaces:**
- Produces: `Job(status: str = "separating", result: Optional[dict] = None, detail: Optional[str] = None)`
- Produces: `create_job() -> str` — returns a new job id, status
  `"separating"`.
- Produces: `get_job(job_id: str) -> Optional[Job]`
- Produces: `set_status(job_id: str, status: str) -> None`
- Produces: `set_result(job_id: str, result: dict) -> None` — also sets
  status to `"done"`.
- Produces: `set_failed(job_id: str, detail: str) -> None` — also sets
  status to `"failed"`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_jobs.py
from app.jobs import create_job, get_job, set_failed, set_result, set_status


def test_create_job_starts_in_separating_status():
    job_id = create_job()
    job = get_job(job_id)
    assert job.status == "separating"
    assert job.result is None
    assert job.detail is None


def test_set_status_updates_an_existing_job():
    job_id = create_job()
    set_status(job_id, "arranging")
    assert get_job(job_id).status == "arranging"


def test_set_result_marks_job_done_with_result_payload():
    job_id = create_job()
    set_result(job_id, {"song_id": "abc", "title": "Song", "difficulties": {}})
    job = get_job(job_id)
    assert job.status == "done"
    assert job.result == {"song_id": "abc", "title": "Song", "difficulties": {}}


def test_set_failed_marks_job_failed_with_detail():
    job_id = create_job()
    set_failed(job_id, "boom")
    job = get_job(job_id)
    assert job.status == "failed"
    assert job.detail == "boom"


def test_get_job_returns_none_for_unknown_id():
    assert get_job("does-not-exist") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.jobs'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/jobs.py
import threading
import uuid
from dataclasses import dataclass
from typing import Optional

_lock = threading.Lock()
_jobs: dict[str, "Job"] = {}


@dataclass
class Job:
    status: str = "separating"
    result: Optional[dict] = None
    detail: Optional[str] = None


def create_job() -> str:
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = Job()
    return job_id


def get_job(job_id: str) -> Optional[Job]:
    with _lock:
        return _jobs.get(job_id)


def set_status(job_id: str, status: str) -> None:
    with _lock:
        _jobs[job_id].status = status


def set_result(job_id: str, result: dict) -> None:
    with _lock:
        job = _jobs[job_id]
        job.status = "done"
        job.result = result


def set_failed(job_id: str, detail: str) -> None:
    with _lock:
        job = _jobs[job_id]
        job.status = "failed"
        job.detail = detail
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_jobs.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/jobs.py backend/tests/test_jobs.py
git commit -m "feat: add in-memory async job store"
```

## Task 3: Harmony-stem mixing and the pipeline orchestrator

**Files:**
- Create: `backend/app/arrange_pipeline.py`
- Test: `backend/tests/test_arrange_pipeline.py`

**Interfaces:**
- Consumes: `separate_stems`/`Stems` (`app.separation`), `extract_melody_part`
  (`app.melody.extract`), `detect_chords` (`app.chords.detect`),
  `generate_lh_variants` (`app.arrangement.engine`), `build_grand_staff_score`
  (`app.notation.hand_split`), `export_musicxml` (`app.export`),
  `write_metadata`/`evict_oldest_songs` (`app.storage`), `set_status`/
  `set_result`/`set_failed` (`app.jobs`, Task 2).
- Produces: `mix_wav_files(path_a: Path, path_b: Path, dest: Path) -> Path`
  — sums two WAV files sample-for-sample, normalized to avoid clipping.
- Produces: `run_arrange_pipeline(job_id: str, audio_path: str, title: str, source_type: str, source_url: Optional[str], song_id: str, dest_dir: Path) -> None`
  — the full pipeline orchestrator; catches all exceptions internally and
  routes them to `set_failed` rather than raising (it runs in a
  background task, with no request context left to raise into). Not unit
  tested directly in this task — Task 4's API-layer tests exercise it
  through monkeypatched stage functions, matching this codebase's
  established API-test pattern.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_arrange_pipeline.py
import numpy as np
from scipy.io import wavfile

from app.arrange_pipeline import mix_wav_files


def test_mix_wav_files_sums_two_tones_without_clipping(tmp_path):
    sample_rate = 22050
    duration_s = 0.5
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)

    tone_a = (0.5 * np.sin(2 * np.pi * 220.0 * t) * 32767).astype(np.int16)
    tone_b = (0.5 * np.sin(2 * np.pi * 440.0 * t) * 32767).astype(np.int16)

    path_a = tmp_path / "a.wav"
    path_b = tmp_path / "b.wav"
    wavfile.write(str(path_a), sample_rate, tone_a)
    wavfile.write(str(path_b), sample_rate, tone_b)

    dest = tmp_path / "mixed.wav"
    result_path = mix_wav_files(path_a, path_b, dest)

    assert result_path == dest
    rate, mixed_audio = wavfile.read(str(dest))
    assert rate == sample_rate
    assert len(mixed_audio) == len(tone_a)
    assert np.max(np.abs(mixed_audio)) <= 32767
    assert np.max(np.abs(mixed_audio)) > 0  # not silent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.arrange_pipeline'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/arrange_pipeline.py
import copy
import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.io import wavfile

from app.arrangement.engine import generate_lh_variants
from app.chords.detect import detect_chords
from app.export import export_musicxml
from app.jobs import set_failed, set_result, set_status
from app.melody.extract import extract_melody_part
from app.notation.hand_split import build_grand_staff_score
from app.separation.separator import separate_stems
from app.storage import evict_oldest_songs, write_metadata


def mix_wav_files(path_a: Path, path_b: Path, dest: Path) -> Path:
    """Sum two WAV files sample-for-sample into dest, normalizing to avoid
    clipping. Used to combine the bass+other stems into a single harmony
    signal for chord detection."""
    rate_a, audio_a = wavfile.read(str(path_a))
    _rate_b, audio_b = wavfile.read(str(path_b))

    n = min(len(audio_a), len(audio_b))
    mixed = audio_a[:n].astype(np.float64) + audio_b[:n].astype(np.float64)
    peak = np.max(np.abs(mixed))
    if peak > 0:
        mixed = mixed / peak * 32767

    wavfile.write(str(dest), rate_a, mixed.astype(np.int16))
    return dest


def run_arrange_pipeline(
    job_id: str,
    audio_path: str,
    title: str,
    source_type: str,
    source_url: Optional[str],
    song_id: str,
    dest_dir: Path,
) -> None:
    try:
        set_status(job_id, "separating")
        stems = separate_stems(audio_path, dest_dir / "stems")

        set_status(job_id, "extracting_melody")
        rh = extract_melody_part(str(stems.vocals))

        set_status(job_id, "detecting_chords")
        harmony_path = mix_wav_files(stems.bass, stems.other, dest_dir / "stems" / "harmony.wav")
        chords = detect_chords(str(harmony_path))
        if not chords:
            raise ValueError("No chords detected")

        set_status(job_id, "arranging")
        variants = generate_lh_variants(chords)

        difficulties = {}
        for tier, lh_part in (("easy", variants.easy), ("medium", variants.medium), ("hard", variants.hard)):
            score = build_grand_staff_score(copy.deepcopy(rh), lh_part, title=title)
            export_musicxml(score, dest_dir / f"{tier}.musicxml")
            difficulties[tier] = {"musicxml_url": f"/storage/{song_id}/{tier}.musicxml"}

        write_metadata(song_id, title=title, source_type=source_type, source_url=source_url, pipeline="arrange")
        evict_oldest_songs()

        set_result(job_id, {"song_id": song_id, "title": title, "difficulties": difficulties})
    except Exception as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        set_failed(job_id, str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add backend/app/arrange_pipeline.py backend/tests/test_arrange_pipeline.py
git commit -m "feat: add harmony-mixing helper and arrange pipeline orchestrator"
```

## Task 4: `POST /arrange` and `GET /arrange/{job_id}`

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `create_job`/`get_job` (`app.jobs`, Task 2),
  `run_arrange_pipeline` (`app.arrange_pipeline`, Task 3), `ingest`
  (`app.ingestion.normalize`, existing, unmodified).
- Produces: `POST /arrange` → `202 {"job_id": str, "status": "processing"}`
- Produces: `GET /arrange/{job_id}` → `200`, one of three shapes: while
  running, `{"status": "separating"|"extracting_melody"|"detecting_chords"|"arranging"}`;
  on failure, `{"status": "failed", "detail": str}`; on success, the
  `TranscribeResponse`-shaped `{"song_id", "title", "difficulties"}` (no
  `"status"` key at all — identical shape to `/transcribe`'s response).
  `404` if `job_id` is unknown.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_api.py`:

```python
import time

from app.arrangement.types import ChordSymbol
from app.separation.types import Stems


def test_arrange_full_job_lifecycle_returns_transcribe_shaped_result(monkeypatch, synthetic_piano_wav):
    import app.arrange_pipeline as pipeline_module
    from music21 import note, stream

    fake_rh = stream.Part(id="RH")
    fake_rh.insert(0, note.Note("C5"))

    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=Path("/fake/vocals.wav"), drums=Path("/fake/drums.wav"),
            bass=Path("/fake/bass.wav"), other=Path("/fake/other.wav"),
        ),
    )
    monkeypatch.setattr(pipeline_module, "mix_wav_files", lambda a, b, dest: dest)
    monkeypatch.setattr(pipeline_module, "extract_melody_part", lambda audio_path: fake_rh)
    monkeypatch.setattr(
        pipeline_module, "detect_chords",
        lambda audio_path: [ChordSymbol(start=0.0, duration=1.0, root=0, quality="major")],
    )

    with open(synthetic_piano_wav, "rb") as f:
        response = client.post("/arrange", files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "processing"
    job_id = body["job_id"]

    result = None
    for _ in range(50):
        payload = client.get(f"/arrange/{job_id}").json()
        if "song_id" in payload or payload.get("status") == "failed":
            result = payload
            break
        time.sleep(0.05)

    assert result is not None, "job did not complete in time"
    assert set(result["difficulties"].keys()) == {"easy", "medium", "hard"}
    song_id = result["song_id"]
    for tier in ("easy", "medium", "hard"):
        assert (STORAGE_ROOT / song_id / f"{tier}.musicxml").exists()


def test_arrange_job_failure_sets_failed_status_with_detail(monkeypatch, synthetic_piano_wav):
    import app.arrange_pipeline as pipeline_module

    def boom(audio_path, output_dir):
        raise RuntimeError("separation blew up")

    monkeypatch.setattr(pipeline_module, "separate_stems", boom)

    with open(synthetic_piano_wav, "rb") as f:
        response = client.post("/arrange", files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")})
    job_id = response.json()["job_id"]

    result = None
    for _ in range(50):
        payload = client.get(f"/arrange/{job_id}").json()
        if "song_id" in payload or payload.get("status") == "failed":
            result = payload
            break
        time.sleep(0.05)

    assert result == {"status": "failed", "detail": "separation blew up"}
    assert not any(STORAGE_ROOT.iterdir())


def test_arrange_status_returns_404_for_unknown_job():
    response = client.get("/arrange/does-not-exist")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -v -k arrange`
Expected: FAIL — `404 Not Found` for the `/arrange` POST (route doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

In `backend/app/main.py`, add `BackgroundTasks` to the existing `fastapi`
import line:

```python
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
```

Add these two imports alongside the existing `app.*` imports:

```python
from app.arrange_pipeline import run_arrange_pipeline
from app.jobs import create_job, get_job
```

Add this response model alongside the existing `TranscribeResponse`/
`SongSummary` models:

```python
class ArrangeSubmitResponse(BaseModel):
    job_id: str
    status: str
```

Add these two routes after the existing `/transcribe` route:

```python
@app.post("/arrange", response_model=ArrangeSubmitResponse, status_code=202)
async def arrange(
    background_tasks: BackgroundTasks,
    audio_file: Optional[UploadFile] = File(None),
    youtube_url: Optional[str] = Form(None),
    spotify_url: Optional[str] = Form(None),
) -> ArrangeSubmitResponse:
    song_id = new_song_id()
    dest_dir = song_dir(song_id)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            upload_tmp_path = None
            upload_filename = None
            if audio_file is not None:
                upload_tmp_path = Path(tmp) / Path(audio_file.filename or "upload").name
                upload_tmp_path.write_bytes(await audio_file.read())
                upload_filename = audio_file.filename

            try:
                ingested = ingest(
                    dest_dir,
                    uploaded_file_path=upload_tmp_path,
                    uploaded_filename=upload_filename,
                    youtube_url=youtube_url,
                    spotify_url=spotify_url,
                    spotify_client_id=SPOTIFY_CLIENT_ID,
                    spotify_client_secret=SPOTIFY_CLIENT_SECRET,
                    max_duration_seconds=MAX_DURATION_SECONDS,
                )
            except IngestionError as exc:
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        duration = librosa.get_duration(path=str(ingested.path))
        if duration > MAX_DURATION_SECONDS:
            raise HTTPException(status_code=413, detail="Audio exceeds the 10-minute duration cap")
    except Exception:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise

    job_id = create_job()
    background_tasks.add_task(
        run_arrange_pipeline,
        job_id=job_id,
        audio_path=str(ingested.path),
        title=ingested.title,
        source_type=ingested.source_type,
        source_url=ingested.source_url,
        song_id=song_id,
        dest_dir=dest_dir,
    )
    return ArrangeSubmitResponse(job_id=job_id, status="processing")


@app.get("/arrange/{job_id}")
def arrange_status(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "done":
        return job.result
    if job.status == "failed":
        return {"status": "failed", "detail": job.detail}
    return {"status": job.status}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -v`
Expected: PASS — the full existing `test_api.py` suite, plus the 3 new
`/arrange` tests.

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all tests pass, nothing existing broken.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_api.py
git commit -m "feat: wire POST /arrange and GET /arrange/{job_id} async job endpoints"
```

## Out of Scope for This Plan

- Frontend: the "Any song" input-mode toggle, progress-indicator polling
  UI, and failure message display — a separate follow-up plan, per the
  spec's "Frontend" section.
- Persisted (non-in-memory) job storage, job expiry/cleanup policy for
  jobs that are never polled to completion — the spec explicitly leaves
  this to the Phase 4 implementation plan's discretion; in-memory is the
  chosen, simplest-for-personal-use answer here, and cleanup isn't
  addressed further.
- Tuning pipeline quality (separation parameters, chord-detection margins,
  arrangement voicings) against real songs — that's Phase 5, requiring
  by-ear judgment against real material, not something to guess at here.
