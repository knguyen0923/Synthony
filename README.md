# Synthony

[![CI](https://github.com/knguyen0923/Synthony/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/knguyen0923/Synthony/actions/workflows/ci.yml)

Synthony turns audio into practice-ready piano sheet music at three
difficulty tiers — Easy, Medium, and Hard. Give it a file upload, a
YouTube link, a Spotify link, or a scanned QR code pointing at one of those
links, and it returns three MusicXML scores rendered in the browser.

Two pipelines, picked explicitly by the user in the frontend's input
screen:

- **Solo piano recording** (Spec 1, `POST /transcribe`) — audio that
  already contains a solo piano performance. See
  [`docs/superpowers/specs/2026-08-31-solo-piano-pipeline-design.md`](docs/superpowers/specs/2026-08-31-solo-piano-pipeline-design.md).
- **Any song** (Spec 2, `POST /arrange`) — a full mixed-down song (vocals,
  drums, bass, whatever else) with no isolated piano at all. Separates the
  mix into stems and builds an original two-hand arrangement: the vocal
  melody becomes the right hand, a real transcription of the harmonic
  accompaniment (bass + everything else that isn't vocals/drums) becomes
  the left hand. See
  [`docs/superpowers/specs/2026-09-01-any-song-arrangement-design.md`](docs/superpowers/specs/2026-09-01-any-song-arrangement-design.md)
  (design) and
  [`docs/superpowers/specs/2026-09-02-lh-true-transcription-design.md`](docs/superpowers/specs/2026-09-02-lh-true-transcription-design.md)
  (a later revision to how the left hand is generated — see that doc's
  note on the original design's now-superseded approach).

## Status

Both pipelines work end-to-end and are real-audio verified (one solo
piano recording, three real full songs, re-run before/after every
pipeline-quality change). Not deployed anywhere — local/Docker-run only,
by explicit choice, not by omission.

**Known limitation:** Spec 2's instrumental fallback (songs with no real
vocal melody) transcribes the bass and "other" stems separately (bass →
LH, other → RH) rather than mixing them and re-splitting by pitch
continuity like the vocal-melody path does — a deliberate trade-off after
real-audio listening found the mixed+split approach caused excessive
hand-flicker on multi-instrument input. The accepted side effect: the
"other" stem's pitch range can occasionally dip below the bass stem's,
so RH can sit lower than LH on the Hard tier. See
`backend/app/arrange_pipeline.py::_instrumental_variants` and
[`docs/superpowers/specs/2026-09-12-hand-split-instrumental-fix-design.md`](docs/superpowers/specs/2026-09-12-hand-split-instrumental-fix-design.md).

## How it works

```
Input (file upload | YouTube link | Spotify link | QR-scanned link)
        │
        ▼
Ingestion — normalizes any input source to a local WAV/MP3
        │
        ├─────────────────────────────────┐
        ▼ (Solo piano recording)          ▼ (Any song)
Transcription — piano-specific model  Stem separation — Demucs:
(piano_transcription_inference,       vocals / drums / bass / other
MAESTRO-trained) audio → raw MIDI             │
(polyphonic)                                  ├─► Melody extraction —
        │                                     │   Basic Pitch on the
Beat-map tempo detection (madmom              │   vocals stem → RH
neural beat tracker; librosa global           │
tempo estimate, then fixed 120 BPM,           └─► LH extraction — Basic
as successive fallbacks)                          Pitch on the bass+other
        │                                         mix, capped to a
Notation — MIDI → music21 grand-staff             plausible simultaneous-
Score via a continuity-aware DP hand              voice count → LH (a real
split (physical hand span, pitch                 transcription, not a
continuity, hand-crossing and                     synthesized pattern)
switching penalties — not a simple            │
top-note-wins rule), each hand capped     Key/tempo detection over the same
to a plausible simultaneous-voice         bass+other mix (chroma + beat-
count                                      tracking, plus a madmom beat map)
        │                                     │
        └─────────────────┬───────────────────┘
                           ▼
       build_grand_staff_score(RH, LH) — shared by both pipelines
                           │
                           ▼
       Difficulty engine — pure Part-level transforms (quantize note
       density, narrow register) derive Easy/Medium from one rich Hard
       base, for both hands, in both pipelines
                           │
                           ▼
                MusicXML export × 3
                           │
                           ▼
Frontend — Easy / Medium / Hard tabs, rendered via OpenSheetMusicDisplay
```

`POST /transcribe` is synchronous — the request blocks until all three
MusicXML variants exist on disk. `POST /arrange` is asynchronous (submit,
then poll `GET /arrange/{job_id}`) since stem separation on CPU can take
real-time-or-slower for a full song.

## Stack

- **Backend:** Python 3.11, FastAPI, [Basic Pitch](https://github.com/spotify/basic-pitch) (ML audio→MIDI, used for Spec 2's RH vocal-melody and LH accompaniment transcription — neither is solo piano audio), [piano_transcription_inference](https://github.com/qiuqiangkong/piano_transcription_inference) (ByteDance's MAESTRO-trained high-resolution piano transcription model, used only for Spec 1's solo-piano audio — meaningfully more accurate than Basic Pitch on real piano recordings), [madmom](https://github.com/CPJKU/madmom) (neural beat tracker driving real tempo detection in both pipelines, with a librosa global-tempo estimate and then a fixed 120 BPM default as successive fallbacks), [Demucs](https://github.com/facebookresearch/demucs) (ML stem separation, Spec 2 only), music21, librosa, yt-dlp, spotipy, pytest.
- **Frontend:** React 18 + Vite + TypeScript, axios, [OpenSheetMusicDisplay](https://opensheetmusicdisplay.org/), html5-qrcode.

## Running it

### Backend

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

YouTube-link ingestion requires `ffmpeg` to be installed and on `PATH` (used by
yt-dlp to extract audio); without it, YouTube-link and Spotify-link input will
fail.

`/transcribe`'s first request downloads the piano transcription model's
~170MB checkpoint to `~/piano_transcription_inference_data/` (one-time, then
cached). Tests exercising this path need `fluidsynth` on `PATH` to render a
realistic test note (skipped otherwise) — install via `brew install fluid-synth`
or your platform's equivalent.

The API listens on `http://localhost:8000`. Rendered scores and source
audio are written under `backend/storage/{song_id}/` (git-ignored, created
at runtime).

Logs are written to both stdout and a rotating file at `backend/logs/app.log`
(git-ignored, 5MB × 3 backups) — useful for diagnosing a crash if the server
was run backgrounded.

Spotify-link input additionally requires a Spotify Developer Dashboard app:

```bash
export SPOTIFY_CLIENT_ID=...
export SPOTIFY_CLIENT_SECRET=...
```

File-upload and YouTube-link input work without these.

A few other environment variables tune runtime behavior, all optional:

- `MAX_CONCURRENT_JOBS` (default `2`) — caps how many heavy ML jobs
  (transcription/separation/arrangement) run at once.
- `LOG_LEVEL` (default `INFO`) — root logger level, e.g. `DEBUG`.
- `JOB_QUEUE_TIMEOUT_SECONDS` (default `1800`) — how long `/arrange` waits
  for a free job slot before failing the job.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Requires Node 18+ (Vite 5). Open the printed URL, pick "Solo piano
recording" or "Any song," then upload a file, paste a YouTube/Spotify
link, or scan a QR code — three tabs (Easy/Medium/Hard) appear once
processing completes. "Any song" jobs take noticeably longer (stem
separation isn't real-time on CPU) and show a progress indicator instead
of a single spinner.

### Tests

```bash
cd backend
source .venv/bin/activate
pytest
```

All external network calls (yt-dlp, Spotify API) are mocked in the test
suite.

```bash
cd frontend
npm test
```

Covers the pure `classifyLink`/`extractErrorMessage` helpers, the
`UploadForm`/`DifficultyTabs`/`InputScreen` component logic, and the
`/arrange` job-polling flow (axios and timers mocked). `ScoreViewer`'s
OpenSheetMusicDisplay rendering and `QrScanButton`'s camera access aren't
covered by automated tests — both stay manually verified in a browser.

GitHub Actions (`.github/workflows/ci.yml`) runs the backend suite and a
frontend lint/test/build check on every push to `main` and on pull requests.

### Docker

```bash
docker compose build && docker compose up
```

This builds and runs both backend (`http://localhost:8000`) and frontend
(`http://localhost:5173`) containers. Put Spotify credentials in a
`backend/.env` file (see `backend/.env.example`) and compose will pick them
up automatically.

**Apple Silicon / arm64:** the backend image builds natively on arm64
Docker hosts. `sphn` (a transitive dependency pulled in via `demucs`) has
no `linux/aarch64` wheel on PyPI, so the Dockerfile installs a Rust
toolchain (via rustup), `cmake`, `libopus-dev`, and `maturin` before the
`requirements.txt` install so pip can build it from source instead.

## API

`GET /health` — liveness/readiness check:

```json
{
  "status": "ok",
  "ffmpeg_available": true,
  "piano_model_downloaded": false
}
```

`ffmpeg_available` reflects whether `ffmpeg` is on `PATH` (see the Backend
section above); `piano_model_downloaded` is `false` until `/transcribe`'s
first request has downloaded the piano transcription checkpoint.

`POST /transcribe` — one of `audio_file` (multipart upload), `youtube_url`,
or `spotify_url` (form fields). Returns:

```json
{
  "song_id": "uuid4",
  "title": "...",
  "difficulties": {
    "easy":   { "musicxml_url": "/storage/{song_id}/easy.musicxml" },
    "medium": { "musicxml_url": "/storage/{song_id}/medium.musicxml" },
    "hard":   { "musicxml_url": "/storage/{song_id}/hard.musicxml" }
  }
}
```

Audio is capped at 10 minutes server-side (`413` if exceeded). It can also
return `503` if no concurrent job slot is available (see `MAX_CONCURRENT_JOBS`
below) — the caller should retry later. Tempo is detected per-song from
a real beat map (madmom's neural beat tracker, with a librosa global-tempo
estimate and then a fixed 120 BPM default as successive fallbacks).

`POST /arrange` — same input fields as `/transcribe`. Returns `202`
immediately:

```json
{ "job_id": "uuid4", "status": "queued" }
```

`GET /arrange/{job_id}` — poll for status. While running:

```json
{ "status": "queued" | "separating" | "extracting_melody" | "detecting_key" | "arranging" }
```

When done, the same `{song_id, title, difficulties}` shape `/transcribe`
returns (so the frontend's result view needs no pipeline-specific
branching). On failure, `{"status": "failed", "detail": "..."}`.

Audio is capped at 10 minutes server-side. Tempo and key are both
detected per-song from the separated bass+other stems (chroma analysis +
beat-tracking); time signature is assumed fixed at 4/4.

## Project layout

```
backend/app/
  ingestion/       file upload, YouTube download, Spotify resolution — shared by both pipelines
  transcription/   audio → NoteEvents: Basic Pitch (Spec 2's vocal/harmony stems) and
                     piano_transcription_inference (Spec 1's solo-piano audio)
  tempo/           real beat-map tempo detection (madmom neural beat tracker, with
                     librosa/fixed-BPM fallbacks) — shared by both pipelines
  notation/        NoteEvent → grand-staff music21 Score: hand_split.py (assembly,
                     beat-map-aware rhythm, dynamic clef changes), hand_assignment.py
                     (continuity-aware DP RH/LH split), voice_cap.py (per-hand
                     simultaneous-voice capping)
  difficulty/       quantize_part / shift_into_range (both hands, both pipelines) +
                     easy.py / medium.py / hard.py — Spec 1's own Score → Score pipeline
  main.py          POST /transcribe and POST /arrange wiring
  export.py        Score → MusicXML
  storage.py       song IDs, storage directories, metadata

  # Spec 2 ("Any song") only:
  separation/      Demucs wrapper — mix → vocals/drums/bass/other stems
  melody/          vocal stem → RH NoteEvents (Basic Pitch + monophonic reduction)
  lh/              bass+other stem mix → LH NoteEvents (Basic Pitch + polyphony capping)
  chords/          key + tempo detection over the bass+other mix (chroma, beat-tracking)
  arrange_pipeline.py   the full Spec 2 pipeline, run as a background job
  jobs.py          in-memory async job status/result tracking

frontend/src/
  api/             typed clients for POST /transcribe and POST /arrange (incl. job polling)
  components/      InputScreen (mode toggle), UploadForm, QrScanButton, ScoreViewer,
                    DifficultyTabs, HistoryTab
  App.tsx          top-level flow: pick a mode → upload/scan → tabs
```
