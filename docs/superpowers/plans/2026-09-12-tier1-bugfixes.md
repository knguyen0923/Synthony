# Tier 1 Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the real, concrete bugs found during a full-codebase discovery sweep (backend `/code-review`, error-handling audit, frontend `/code-review`) — self-hosted personal-project scope, no auth/multi-tenant concerns.

**Architecture:** Small, independent, surgical fixes across ingestion error-handling (backend), the instrumental hand-assignment guard (backend), and several frontend state/lifecycle bugs (React). No architectural changes — every fix here is a targeted correction to existing, already-identified broken behavior.

**Tech Stack:** Python 3.11/FastAPI (backend), TypeScript/React 18/Vitest (frontend).

**Spec:** None — findings came from a verified discovery sweep (code-review + error-handling audit agents, several claims confirmed by direct execution), not a design brainstorm. This plan documents the fix for each confirmed finding directly.

## Global Constraints

- TDD is non-negotiable for backend Python work — write the failing test first.
- Run the full backend suite (`cd backend && ./.venv/bin/python -m pytest -v`) before any backend commit.
- Run the full frontend suite (`cd frontend && npm test`) before any frontend commit — note: this sandbox's system Node is v16 and vitest requires v18+; use `nvm use 22` (available in this environment) before running `npm test`, or trust CI (already configured for Node 18) if a modern Node isn't available.
- Self-hosted, no-auth scope: none of these fixes should add authentication, rate limiting, or multi-tenant isolation — that's explicitly out of scope.

---

## File Structure

- **Modify:** `backend/app/ingestion/spotify.py` — catch `SpotifyOauthError` in addition to `SpotifyException`; guard `_search_youtube`'s unguarded yt-dlp call (Task 1).
- **Modify:** `backend/app/main.py` — wrap `librosa.get_duration` in a try/except that produces a clean 422; move `song_dir()` inside the try block with a null-safe cleanup guard (Task 1).
- **Modify:** `backend/app/separation/separator.py` — surface Demucs's captured stderr on subprocess failure (Task 1).
- **Modify:** `backend/app/arrange_pipeline.py` — log a warning when either hand of the instrumental split produces zero notes, instead of silently shipping a blank staff with no signal (Task 2).
- **Modify:** `frontend/src/components/QrScanButton.tsx` — reset `scanning` on camera-access failure; guard against a duplicate scan-success firing before `stop()` takes effect; reset `error` before a new scan attempt; guard the async continuation against a stale/unmounted effect (Task 3).
- **Modify:** `frontend/src/components/UploadForm.tsx` — reentrancy guard against double-submit; reset the file input so re-selecting the same file works after a failure; guard state updates against unmount (Task 3).
- **Modify:** `frontend/src/components/DifficultyTabs.tsx` — guard against a missing difficulty tier instead of crashing (Task 3).
- **Modify:** `frontend/src/components/ScoreViewer.tsx` — wrap `osmd.load` in a try/catch, surfacing a user-visible error instead of a silent blank screen (Task 3).
- **Modify:** `frontend/src/components/HistoryTab.tsx` — guard the mount-time fetch against unmount (Task 3).
- **Modify:** `frontend/src/components/InputScreen.tsx` — give `UploadForm`/`QrScanButton` distinct `key`s per mode so switching modes mid-request cleanly unmounts the old instance instead of silently reusing it with new props (Task 3).

No new files, no new modules.

---

### Task 1: Backend ingestion error-handling hardening

**Files:**
- Modify: `backend/app/ingestion/spotify.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/separation/separator.py`
- Test: `backend/tests/test_ingestion_spotify.py` (or wherever existing Spotify ingestion tests live — check first), `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `spotipy.oauth2.SpotifyOauthError` (confirmed via direct execution: not a subclass of `spotipy.SpotifyException`, so must be caught separately).
- Produces: no signature changes — `resolve_and_download`, `_search_youtube`, `_ingest_and_validate_duration` all keep their existing signatures; only their internal error handling changes.

- [ ] **Step 1: Find or confirm the existing Spotify ingestion test file**

Run: `cd backend && grep -rl "resolve_and_download\|SpotifyClientCredentials" tests/`

Use whatever file that finds as the target for the new tests below (append to it). If none exists, create `backend/tests/test_ingestion_spotify.py`.

- [ ] **Step 2: Write the failing tests**

Match `test_spotify.py`'s existing style exactly (`from app.ingestion import spotify as spotify_module`, `monkeypatch.setattr(spotify_module, ...)` — not `unittest.mock.patch`):

```python
def test_resolve_and_download_wraps_oauth_errors_as_resolution_errors(monkeypatch, tmp_path):
    """Confirmed by direct execution: SpotifyClientCredentials(...) raises
    SpotifyOauthError when client_id/client_secret are unset (the default,
    unconfigured state) -- SpotifyOauthError is NOT a subclass of
    spotipy.SpotifyException, so the pre-existing try/except (which only
    caught SpotifyException around client.track()) never caught it, and it
    propagated as a raw, unhandled exception."""
    def _raise_oauth_error(**kwargs):
        raise spotipy.oauth2.SpotifyOauthError("no client credentials set")

    monkeypatch.setattr(spotify_module, "SpotifyClientCredentials", _raise_oauth_error)

    with pytest.raises(SpotifyResolutionError):
        resolve_and_download(
            "https://open.spotify.com/track/abc123",
            tmp_path,
            "",
            "",
        )


def test_search_youtube_wraps_download_errors_as_resolution_errors(monkeypatch):
    """_search_youtube's yt_dlp.YoutubeDL(...).extract_info(...) call had no
    try/except anywhere in its call chain, unlike the structurally identical
    call in download_audio three lines below it."""
    from app.ingestion.spotify import _search_youtube

    class _FailingYoutubeDL:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, *args, **kwargs):
            raise spotify_module.yt_dlp.utils.DownloadError("network error")

    monkeypatch.setattr(spotify_module.yt_dlp, "YoutubeDL", _FailingYoutubeDL)

    with pytest.raises(SpotifyResolutionError):
        _search_youtube("some query")
```

These use `spotify_module` (`from app.ingestion import spotify as spotify_module`) and `spotipy` — both already imported at the top of `test_spotify.py`; add `import yt_dlp` there too if it isn't already present (`_search_youtube` currently does a local `import yt_dlp` inside the function itself — Step 5 below removes that local import since the module-level one is used instead, see the exact diff).

- [ ] **Step 3: Run the tests, verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/ -k "resolve_and_download_wraps_oauth or search_youtube_wraps" -v`
Expected: FAIL — `test_resolve_and_download_wraps_oauth_errors_as_resolution_errors` fails because `SpotifyOauthError` propagates unhandled (not converted to `SpotifyResolutionError`); `test_search_youtube_wraps_download_errors_as_resolution_errors` fails because `_search_youtube` has no try/except at all.

- [ ] **Step 4: Implement — fix `resolve_and_download`**

In `backend/app/ingestion/spotify.py`, change:

```python
import re
from pathlib import Path
from typing import Optional, Tuple

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
```

to:

```python
import re
from pathlib import Path
from typing import Optional, Tuple

import spotipy
import yt_dlp
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOauthError
```

(hoisting `yt_dlp` to a module-level import — `_search_youtube` currently does a local `import yt_dlp` inside the function; Step 5 below removes that local import now that it's redundant, and the module-level import lets tests monkeypatch `spotify_module.yt_dlp.YoutubeDL` directly, consistent with how `test_spotify.py` already patches other module-level attributes.)

Then change:

```python
    auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    client = spotipy.Spotify(auth_manager=auth_manager)
    try:
        track = client.track(track_id)
    except spotipy.SpotifyException as exc:
        raise SpotifyResolutionError(f"Could not resolve Spotify track: {spotify_url}") from exc
```

to:

```python
    try:
        auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        client = spotipy.Spotify(auth_manager=auth_manager)
        track = client.track(track_id)
    except (spotipy.SpotifyException, SpotifyOauthError) as exc:
        raise SpotifyResolutionError(f"Could not resolve Spotify track: {spotify_url}") from exc
```

- [ ] **Step 5: Implement — fix `_search_youtube`**

In `backend/app/ingestion/spotify.py`, change:

```python
def _search_youtube(query: str) -> Optional[str]:
    import yt_dlp

    options = {"quiet": True, "default_search": "ytsearch1", "noplaylist": True}
    with yt_dlp.YoutubeDL(options) as ydl:
        result = ydl.extract_info(query, download=False)
        entries = result.get("entries") or []
        if not entries:
            return None
        return entries[0]["webpage_url"]
```

to:

```python
def _search_youtube(query: str) -> Optional[str]:
    options = {"quiet": True, "default_search": "ytsearch1", "noplaylist": True}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            result = ydl.extract_info(query, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise SpotifyResolutionError(f"Could not search YouTube for: {query}") from exc

    entries = (result or {}).get("entries") or []
    if not entries:
        return None
    return entries[0]["webpage_url"]
```

- [ ] **Step 6: Run the tests, verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/ -k "resolve_and_download_wraps_oauth or search_youtube_wraps" -v`
Expected: PASS.

- [ ] **Step 7: Write the failing test for the librosa/upload-validation gap**

Add to `backend/tests/test_api.py` (check the existing imports/fixtures in that file first and match its style — it already has a FastAPI `TestClient` fixture for `/transcribe`/`/arrange`):

```python
def test_transcribe_rejects_non_audio_upload_with_a_clean_422():
    """Confirmed by direct execution: a text file renamed .mp3 passes
    upload.py's extension-only validation, then librosa.get_duration raises
    audioread.exceptions.NoBackendError -- previously uncaught (outside the
    try/except IngestionError block in _ingest_and_validate_duration),
    surfacing as a raw 500 instead of a clean 4xx."""
    response = client.post(
        "/transcribe",
        files={"audio_file": ("fake.mp3", b"this is not audio data, just text bytes", "audio/mpeg")},
    )
    assert response.status_code == 422
```

`test_api.py` already has a module-level `client = TestClient(app)` (line 4) — use that directly, no fixture needed. Match whatever existing test in that file is closest to this shape for any additional setup/teardown conventions (e.g. temp storage cleanup) before adding this one.

- [ ] **Step 8: Run it, verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k non_audio_upload -v`
Expected: FAIL with a 500, not 422 (or an unhandled exception surfacing as a test error).

- [ ] **Step 9: Implement — wrap `librosa.get_duration` and move `song_dir()` inside the try block**

In `backend/app/main.py`, change:

```python
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

    return ingested
```

to:

```python
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

    try:
        duration = librosa.get_duration(path=str(ingested.path))
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="Could not read audio file — it may be corrupt or an unsupported format",
        ) from exc
    if duration > MAX_DURATION_SECONDS:
        raise HTTPException(status_code=413, detail="Audio exceeds the 10-minute duration cap")

    return ingested
```

Then, in both `transcribe` and `arrange`, move the `dest_dir = song_dir(song_id)` call inside the `try:` block with a null-safe cleanup guard. Change (in `transcribe`):

```python
    song_id = new_song_id()
    dest_dir = song_dir(song_id)

    try:
        ingested = await _ingest_and_validate_duration(dest_dir, audio_file, youtube_url, spotify_url)
```

to:

```python
    song_id = new_song_id()
    dest_dir: Optional[Path] = None

    try:
        dest_dir = song_dir(song_id)
        ingested = await _ingest_and_validate_duration(dest_dir, audio_file, youtube_url, spotify_url)
```

And change both of its `except` blocks' cleanup calls from:

```python
        shutil.rmtree(dest_dir, ignore_errors=True)
```

to:

```python
        if dest_dir is not None:
            shutil.rmtree(dest_dir, ignore_errors=True)
```

(there are two such lines in `transcribe`'s except blocks — update both). Apply the identical change to `arrange`:

```python
    song_id = new_song_id()
    dest_dir = song_dir(song_id)

    try:
        ingested = await _ingest_and_validate_duration(dest_dir, audio_file, youtube_url, spotify_url)
    except Exception:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise
```

to:

```python
    song_id = new_song_id()
    dest_dir: Optional[Path] = None

    try:
        dest_dir = song_dir(song_id)
        ingested = await _ingest_and_validate_duration(dest_dir, audio_file, youtube_url, spotify_url)
    except Exception:
        if dest_dir is not None:
            shutil.rmtree(dest_dir, ignore_errors=True)
        raise
```

- [ ] **Step 10: Run the test, verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k non_audio_upload -v`
Expected: PASS.

- [ ] **Step 11: Implement — surface Demucs's stderr on failure**

In `backend/app/separation/separator.py`, change:

```python
def separate_stems(audio_path: str, output_dir: Path) -> Stems:
    """Run Demucs 4-stem separation on audio_path, writing vocals/drums/
    bass/other WAV files under output_dir, and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [sys.executable, "-m", "demucs.separate", "-n", MODEL_NAME, "-o", str(output_dir), audio_path],
        check=True,
        capture_output=True,
    )
```

to:

```python
def separate_stems(audio_path: str, output_dir: Path) -> Stems:
    """Run Demucs 4-stem separation on audio_path, writing vocals/drums/
    bass/other WAV files under output_dir, and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            [sys.executable, "-m", "demucs.separate", "-n", MODEL_NAME, "-o", str(output_dir), audio_path],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "(no stderr captured)"
        raise RuntimeError(f"Demucs stem separation failed: {stderr}") from exc
```

- [ ] **Step 12: Run the full backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS, zero failures, zero collection errors.

- [ ] **Step 13: Commit**

```bash
cd /Users/knguyen/VSC/Synthony
git add backend/app/ingestion/spotify.py backend/app/main.py backend/app/separation/separator.py backend/tests/
git commit -m "$(cat <<'EOF'
fix: harden ingestion error handling against bad input and default config

Confirmed by direct execution: Spotify ingestion is unconditionally broken
(raw 500) in the default unconfigured state, since SpotifyOauthError isn't
a subclass of SpotifyException and the existing try/except never caught
it. Also fixes: _search_youtube's unguarded yt-dlp call, a non-audio/
corrupt upload surfacing as a raw 500 instead of a clean 422 (librosa
decode failure wasn't caught), and Demucs subprocess failures discarding
their captured stderr, making failed /arrange jobs hard to debug.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Instrumental empty-hand observability

**Files:**
- Modify: `backend/app/arrange_pipeline.py`
- Test: `backend/tests/test_arrange_pipeline.py`

**Interfaces:**
- Consumes: `logging.Logger` (`logger`, already defined at module level in `arrange_pipeline.py`).
- Produces: no signature/behavior change to `_instrumental_variants` — same return shape, same exceptions. Adds only a log line.

The `code-review` finding here was: `_instrumental_variants`'s empty-content guard (`if not rh_notes and not lh_notes: raise ValueError(...)`) only fails when BOTH hands produce zero notes — a track where only one stem (e.g. "other") is genuinely silent (a bass-only passage, or a real extraction gap) succeeds with a fully blank staff for that hand, with no signal anywhere that anything unusual happened. Raising in this case would be wrong (a genuinely bass-only instrumental passage is legitimate content, not a bug), but shipping silently with zero observability is also wrong — the fix is a log line, not a stricter guard.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_arrange_pipeline.py`:

```python
def test_instrumental_variants_logs_a_warning_when_one_hand_is_empty(monkeypatch, caplog):
    import logging
    import app.arrange_pipeline as pipeline_module

    other_notes = [NoteEvent(start=0.0, end=1.0, pitch=60, velocity=0.5)]
    monkeypatch.setattr(
        pipeline_module, "transcribe_audio_to_notes", _fake_transcribe_by_path([], other_notes)
    )

    with caplog.at_level(logging.WARNING, logger="app.arrange_pipeline"):
        pipeline_module._instrumental_variants("fake/bass.wav", "fake/other.wav", 0.5)

    assert any("bass" in record.message.lower() and "empty" in record.message.lower() for record in caplog.records)
```

(`_fake_transcribe_by_path` already exists in this test file from the earlier stem-split fix — reuse it, don't redefine it.)

- [ ] **Step 2: Run it, verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -k logs_a_warning_when_one_hand_is_empty -v`
Expected: FAIL — no warning is currently logged.

- [ ] **Step 3: Implement**

In `backend/app/arrange_pipeline.py`'s `_instrumental_variants`, change:

```python
    rh_notes = transcribe_audio_to_notes(other_path, minimum_note_length=LH_MINIMUM_NOTE_LENGTH_MS)
    lh_notes = transcribe_audio_to_notes(bass_path, minimum_note_length=LH_MINIMUM_NOTE_LENGTH_MS)
    if not rh_notes and not lh_notes:
        raise ValueError("No harmonic content detected")
```

to:

```python
    rh_notes = transcribe_audio_to_notes(other_path, minimum_note_length=LH_MINIMUM_NOTE_LENGTH_MS)
    lh_notes = transcribe_audio_to_notes(bass_path, minimum_note_length=LH_MINIMUM_NOTE_LENGTH_MS)
    if not rh_notes and not lh_notes:
        raise ValueError("No harmonic content detected")
    if not rh_notes:
        logger.warning("instrumental arrange: other-stem transcription produced zero notes -- RH will be empty")
    if not lh_notes:
        logger.warning("instrumental arrange: bass-stem transcription produced zero notes -- LH will be empty")
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -k logs_a_warning_when_one_hand_is_empty -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS, zero failures.

- [ ] **Step 6: Commit**

```bash
cd /Users/knguyen/VSC/Synthony
git add backend/app/arrange_pipeline.py backend/tests/test_arrange_pipeline.py
git commit -m "$(cat <<'EOF'
fix: log a warning when one instrumental hand transcribes to zero notes

_instrumental_variants only raises when BOTH stems are empty (a
legitimately bass-only or lead-only passage is real content, not a bug),
but shipped completely silently when just one hand was empty -- no signal
anywhere that anything unusual happened. A log line doesn't change
behavior, just observability, per a code-review finding on this session's
own stem-split fix.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Frontend bug fixes

**Files:**
- Modify: `frontend/src/components/QrScanButton.tsx`
- Modify: `frontend/src/components/UploadForm.tsx`
- Modify: `frontend/src/components/DifficultyTabs.tsx`
- Modify: `frontend/src/components/ScoreViewer.tsx`
- Modify: `frontend/src/components/HistoryTab.tsx`
- Modify: `frontend/src/components/InputScreen.tsx`
- Test: `frontend/src/components/QrScanButton.test.tsx`, `frontend/src/components/UploadForm.test.tsx`, `frontend/src/components/DifficultyTabs.test.tsx` (check which of these test files already exist and extend them; create any that don't)

**Interfaces:**
- No prop-type or exported-function signature changes anywhere in this task — every fix is internal to the component it's in.

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/QrScanButton.test.tsx` does not exist yet — create it. `UploadForm.test.tsx` and `DifficultyTabs.test.tsx` already exist — extend them, matching their existing import/mock style exactly (both already use `@testing-library/react` + `@testing-library/user-event` + `vitest`'s `vi`).

**Create `frontend/src/components/QrScanButton.test.tsx`:**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QrScanButton } from "./QrScanButton";
import type { TranscribeResponse } from "../api/types";

const mockStart = vi.fn();
const mockStop = vi.fn().mockResolvedValue(undefined);

vi.mock("html5-qrcode", () => ({
  Html5Qrcode: vi.fn().mockImplementation(() => ({
    start: mockStart,
    stop: mockStop,
  })),
}));

const RESULT: TranscribeResponse = {
  song_id: "song-1",
  title: "Test Song",
  difficulties: {
    easy: { musicxml_url: "/easy.musicxml" },
    medium: { musicxml_url: "/medium.musicxml" },
    hard: { musicxml_url: "/hard.musicxml" },
  },
};

beforeEach(() => {
  mockStart.mockReset();
  mockStop.mockReset().mockResolvedValue(undefined);
});

describe("QrScanButton", () => {
  it("resets scanning state when the camera fails to start", async () => {
    const user = userEvent.setup();
    mockStart.mockRejectedValue(new Error("permission denied"));

    render(<QrScanButton onSuccess={vi.fn()} submitLink={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Scan QR code" }));

    expect(await screen.findByText("Could not access the camera.")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Scan QR code" })).not.toBeDisabled()
    );
  });

  it("resets any prior error message when starting a new scan", async () => {
    const user = userEvent.setup();
    mockStart.mockRejectedValueOnce(new Error("permission denied"));
    mockStart.mockImplementationOnce(() => new Promise(() => {})); // second attempt hangs deliberately

    render(<QrScanButton onSuccess={vi.fn()} submitLink={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Scan QR code" }));
    expect(await screen.findByText("Could not access the camera.")).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Scan QR code" })).not.toBeDisabled()
    );
    await user.click(screen.getByRole("button", { name: "Scan QR code" }));

    expect(screen.queryByText("Could not access the camera.")).not.toBeInTheDocument();
  });

  it("only processes a scan result once, even if the success callback fires again before stop() resolves", async () => {
    const submitLink = vi.fn().mockResolvedValue(RESULT);
    const onSuccess = vi.fn();
    let fireSuccess: (decodedText: string) => void = () => {};
    mockStart.mockImplementation((_config: unknown, _scanConfig: unknown, successCb: (text: string) => void) => {
      fireSuccess = successCb;
      return Promise.resolve();
    });
    // stop() resolves slowly, mirroring how a real second camera frame could
    // fire the success callback again before the first stop() settles.
    mockStop.mockImplementation(() => new Promise((resolve) => setTimeout(resolve, 20)));

    render(<QrScanButton onSuccess={onSuccess} submitLink={submitLink} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Scan QR code" }));
    await waitFor(() => expect(mockStart).toHaveBeenCalled());

    fireSuccess("decoded-text");
    fireSuccess("decoded-text"); // simulated duplicate frame

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(submitLink).toHaveBeenCalledTimes(1);
  });
});
```

**Add to `frontend/src/components/UploadForm.test.tsx`** (inside the existing `describe("UploadForm", ...)` block, matching its existing `deferred<T>()` helper already defined in that file):

```tsx
  it("ignores a second file-change while the first submission is still in flight", async () => {
    const user = userEvent.setup();
    const { promise, resolve } = deferred<TranscribeResponse>();
    const submitFile = vi.fn().mockReturnValue(promise);
    const file = new File(["fake audio bytes"], "song.mp3", { type: "audio/mpeg" });

    render(<UploadForm onSuccess={vi.fn()} submitFile={submitFile} submitLink={vi.fn()} />);

    const input = screen.getByLabelText("Upload a file") as HTMLInputElement;
    await user.upload(input, file);
    await user.upload(input, file);

    resolve(RESULT);
    await waitFor(() => expect(screen.queryByText("Working…")).not.toBeInTheDocument());
    expect(submitFile).toHaveBeenCalledTimes(1);
  });

  it("resets the file input value after handling so the same file can be re-selected", async () => {
    const user = userEvent.setup();
    const submitFile = vi.fn().mockRejectedValue(new Error("boom"));
    const file = new File(["fake audio bytes"], "song.mp3", { type: "audio/mpeg" });

    render(<UploadForm onSuccess={vi.fn()} submitFile={submitFile} submitLink={vi.fn()} />);

    const input = screen.getByLabelText("Upload a file") as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => expect(input.value).toBe(""));
  });
```

**Add to `frontend/src/components/DifficultyTabs.test.tsx`** (inside the existing `describe("DifficultyTabs", ...)` block):

```tsx
  it("shows a fallback message instead of crashing when the active tier is missing from difficulties", async () => {
    const user = userEvent.setup();
    const resultMissingHard = {
      song_id: "song-1",
      title: "Test Song",
      difficulties: {
        easy: { musicxml_url: "/easy.musicxml" },
        medium: { musicxml_url: "/medium.musicxml" },
        // "hard" intentionally omitted -- simulates a real backend response
        // where one tier failed to generate (TypeScript's Record<Difficulty,
        // DifficultyLink> can't express this, but nothing at runtime
        // enforces it either).
      },
    } as unknown as TranscribeResponse;

    render(<DifficultyTabs result={resultMissingHard} />);
    await user.click(screen.getByRole("tab", { name: "Hard" }));

    expect(screen.queryByTestId("score-viewer")).not.toBeInTheDocument();
    expect(screen.getByText(/isn't available/i)).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run the new tests, verify they fail**

Run (use `nvm use 22` first if the sandbox's default Node is too old — verified in this session that Node 16 makes vitest fail to even start, unrelated to these tests): `cd frontend && npm test`
Expected: the new tests FAIL (or error) against the current code; everything else still passes.

- [ ] **Step 3: Implement — `QrScanButton.tsx`**

Change:

```tsx
      .then(() => {
        if (cancelled) {
          // Unmounted while start() was pending — safe to stop now that it
          // has actually finished starting.
          scanner.stop().catch(() => {});
        } else {
          started = true;
        }
      })
      .catch(() => setError("Could not access the camera."));
```

to:

```tsx
      .then(() => {
        if (cancelled) {
          // Unmounted while start() was pending — safe to stop now that it
          // has actually finished starting.
          scanner.stop().catch(() => {});
        } else {
          started = true;
        }
      })
      .catch(() => {
        setError("Could not access the camera.");
        setScanning(false);
      });
```

Change the success callback to guard against a duplicate invocation before `stop()` takes effect (html5-qrcode can invoke the success callback again for subsequent frames while `stop()` is still pending):

```tsx
    let cancelled = false;
    let started = false;

    scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: 250 },
        async (decodedText) => {
          await scanner.stop();
          setScanning(false);
          setStatusLabel("Working…");
          try {
            const result = await submitLink(decodedText, setStatusLabel);
            onSuccess(result);
          } catch (err) {
            setError(extractErrorMessage(err, "Couldn't process the scanned link."));
          } finally {
            setStatusLabel(null);
          }
        },
```

to:

```tsx
    let cancelled = false;
    let started = false;
    let handled = false;

    scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: 250 },
        async (decodedText) => {
          if (handled) return;
          handled = true;
          await scanner.stop();
          setScanning(false);
          setStatusLabel("Working…");
          try {
            const result = await submitLink(decodedText, (label) => {
              if (!cancelled) setStatusLabel(label);
            });
            if (!cancelled) onSuccess(result);
          } catch (err) {
            if (!cancelled) setError(extractErrorMessage(err, "Couldn't process the scanned link."));
          } finally {
            if (!cancelled) setStatusLabel(null);
          }
        },
```

Finally, reset `error` before starting a new scan. Change:

```tsx
      <button onClick={() => setScanning(true)} disabled={scanning}>
        Scan QR code
      </button>
```

to:

```tsx
      <button
        onClick={() => {
          setError(null);
          setScanning(true);
        }}
        disabled={scanning}
      >
        Scan QR code
      </button>
```

- [ ] **Step 4: Implement — `UploadForm.tsx`**

Add a mounted-ref guard, a reentrancy guard, and the file-input reset. Change:

```tsx
import { useState } from "react";
import type { TranscribeResponse } from "../api/types";
import { extractErrorMessage } from "../api/errors";

interface UploadFormProps {
  onSuccess: (result: TranscribeResponse) => void;
  submitFile: (file: File, onProgress: (label: string) => void) => Promise<TranscribeResponse>;
  submitLink: (url: string, onProgress: (label: string) => void) => Promise<TranscribeResponse>;
}

export function UploadForm({ onSuccess, submitFile, submitLink }: UploadFormProps) {
  const [link, setLink] = useState("");
  const [loading, setLoading] = useState(false);
  const [statusLabel, setStatusLabel] = useState("Working…");
  const [error, setError] = useState<string | null>(null);

  async function run(call: (onProgress: (label: string) => void) => Promise<TranscribeResponse>) {
    setLoading(true);
    setStatusLabel("Working…");
    setError(null);
    try {
      const result = await call(setStatusLabel);
      onSuccess(result);
    } catch (err) {
      setError(extractErrorMessage(err, "Something went wrong processing that audio."));
    } finally {
      setLoading(false);
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    await run((onProgress) => submitFile(file, onProgress));
  }
```

to:

```tsx
import { useEffect, useRef, useState } from "react";
import type { TranscribeResponse } from "../api/types";
import { extractErrorMessage } from "../api/errors";

interface UploadFormProps {
  onSuccess: (result: TranscribeResponse) => void;
  submitFile: (file: File, onProgress: (label: string) => void) => Promise<TranscribeResponse>;
  submitLink: (url: string, onProgress: (label: string) => void) => Promise<TranscribeResponse>;
}

export function UploadForm({ onSuccess, submitFile, submitLink }: UploadFormProps) {
  const [link, setLink] = useState("");
  const [loading, setLoading] = useState(false);
  const [statusLabel, setStatusLabel] = useState("Working…");
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  async function run(call: (onProgress: (label: string) => void) => Promise<TranscribeResponse>) {
    if (loading) return;
    setLoading(true);
    setStatusLabel("Working…");
    setError(null);
    try {
      const result = await call((label) => {
        if (mountedRef.current) setStatusLabel(label);
      });
      if (mountedRef.current) onSuccess(result);
    } catch (err) {
      if (mountedRef.current) {
        setError(extractErrorMessage(err, "Something went wrong processing that audio."));
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const input = event.target;
    const file = input.files?.[0];
    if (!file) return;
    await run((onProgress) => submitFile(file, onProgress));
    input.value = "";
  }
```

- [ ] **Step 5: Implement — `DifficultyTabs.tsx`**

Change:

```tsx
      <ScoreViewer musicXmlUrl={result.difficulties[active].musicxml_url} title={`${result.title} (${active})`} />
    </div>
  );
}
```

to:

```tsx
      {result.difficulties[active] ? (
        <ScoreViewer
          musicXmlUrl={result.difficulties[active].musicxml_url}
          title={`${result.title} (${active})`}
        />
      ) : (
        <p className="difficulty-tabs__missing">This difficulty tier isn't available for this song.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Implement — `ScoreViewer.tsx`**

Change:

```tsx
    (async () => {
      await osmd.load(resolveFullUrl(musicXmlUrl));
      if (!cancelled) {
        osmd.zoom = zoomRef.current;
        osmd.render();
      }
    })();
```

to:

```tsx
    (async () => {
      try {
        await osmd.load(resolveFullUrl(musicXmlUrl));
        if (!cancelled) {
          osmd.zoom = zoomRef.current;
          osmd.render();
        }
      } catch {
        if (!cancelled) {
          setActionError("Couldn't load this score — the file may be missing or corrupt.");
        }
      }
    })();
```

- [ ] **Step 7: Implement — `HistoryTab.tsx`**

Change:

```tsx
  useEffect(() => {
    listSongs()
      .then(setSongs)
      .catch(() => setError("Couldn't load history."));
  }, []);
```

to:

```tsx
  useEffect(() => {
    let cancelled = false;
    listSongs()
      .then((result) => {
        if (!cancelled) setSongs(result);
      })
      .catch(() => {
        if (!cancelled) setError("Couldn't load history.");
      });
    return () => {
      cancelled = true;
    };
  }, []);
```

- [ ] **Step 8: Implement — `InputScreen.tsx`**

Change:

```tsx
      <div className="input-screen__panel">
        {mode === "transcribe" ? (
          <>
            <UploadForm onSuccess={onSuccess} submitFile={transcribeFile} submitLink={transcribeLink} />
            <div className="upload-form__divider">or</div>
            <QrScanButton onSuccess={onSuccess} submitLink={transcribeLink} />
          </>
        ) : (
          <>
            <UploadForm onSuccess={onSuccess} submitFile={arrangeFile} submitLink={arrangeLink} />
            <div className="upload-form__divider">or</div>
            <QrScanButton onSuccess={onSuccess} submitLink={arrangeLink} />
          </>
        )}
      </div>
```

to:

```tsx
      <div className="input-screen__panel">
        {mode === "transcribe" ? (
          <>
            <UploadForm key="transcribe-upload" onSuccess={onSuccess} submitFile={transcribeFile} submitLink={transcribeLink} />
            <div className="upload-form__divider">or</div>
            <QrScanButton key="transcribe-qr" onSuccess={onSuccess} submitLink={transcribeLink} />
          </>
        ) : (
          <>
            <UploadForm key="arrange-upload" onSuccess={onSuccess} submitFile={arrangeFile} submitLink={arrangeLink} />
            <div className="upload-form__divider">or</div>
            <QrScanButton key="arrange-qr" onSuccess={onSuccess} submitLink={arrangeLink} />
          </>
        )}
      </div>
```

This forces React to unmount/remount `UploadForm`/`QrScanButton` on mode switch (same component type at the same tree position was previously being silently reused with new props across a mode change — a `key` change is the standard React idiom to force fresh identity instead).

- [ ] **Step 9: Run the new tests, verify they pass**

Run: `cd frontend && npm test`
Expected: PASS, all tests including the new ones.

- [ ] **Step 10: Commit**

```bash
cd /Users/knguyen/VSC/Synthony
git add frontend/src/components/QrScanButton.tsx frontend/src/components/UploadForm.tsx frontend/src/components/DifficultyTabs.tsx frontend/src/components/ScoreViewer.tsx frontend/src/components/HistoryTab.tsx frontend/src/components/InputScreen.tsx frontend/src/components/*.test.tsx
git commit -m "$(cat <<'EOF'
fix: several frontend state/lifecycle bugs found in a code-review sweep

- QrScanButton: camera-access failure left the scan button permanently
  disabled; a slow stop() could let one scan fire two submissions; a
  stale error message could persist across a new scan attempt.
- UploadForm: no reentrancy guard against a double-submit race; the file
  input never reset, so re-selecting the same file after a failure was a
  silent no-op; state updates could fire after unmount.
- DifficultyTabs: crashed the whole result view if a tier was missing
  from the response instead of showing a fallback message.
- ScoreViewer: a failed MusicXML load (404, corrupt file) showed a
  silent blank screen instead of a visible error.
- HistoryTab: the mount-time song-list fetch had no unmount guard.
- InputScreen: UploadForm/QrScanButton occupied the same tree position
  in both mode branches, so switching modes mid-request silently reused
  the old instance with new props instead of remounting fresh — fixed
  with a per-mode `key`.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

## Deferred (not in scope here)

- `pollArrangeJob`'s underlying network polling doesn't stop after unmount (only the resulting `onSuccess`/state-update side effects are now suppressed via the mounted-ref guard in Task 3) — a full `AbortSignal`-based cancellation would need to thread through `submitFile`/`submitLink`'s shared prop types across both `transcribe.ts` and `arrange.ts`, a bigger change than this pass's bug-fix scope. Revisit alongside Tier 2's polling-utility dedup if it becomes a real problem at personal-project scale.
- Tier 2 (polish/dedup) and Tier 3 (efficiency/caching) — separate plans, per the user's explicit scope decision.
