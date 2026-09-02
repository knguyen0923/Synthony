# Synthony

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

## How it works

```
Input (file upload | YouTube link | Spotify link | QR-scanned link)
        │
        ▼
Ingestion — normalizes any input source to a local WAV/MP3
        │
        ├─────────────────────────────┐
        ▼ (Solo piano recording)      ▼ (Any song)
Transcription — Basic Pitch      Stem separation — Demucs:
audio → raw MIDI (polyphonic)    vocals / drums / bass / other
        │                             │
        ▼                             ├─► Melody extraction — Basic Pitch
Notation — MIDI → music21              │   on the vocals stem → RH
grand-staff Score (melody-aware        │
hand split: highest simultaneous       └─► LH extraction — Basic Pitch on
note = RH, rest = LH)                      the bass+other mix, capped to a
        │                                  plausible simultaneous-voice
        │                                  count → LH (a real
        │                                  transcription, not a
        │                                  synthesized pattern)
        │                             │
        │                        Key/tempo detection over the same
        │                        bass+other mix (chroma + beat-tracking)
        │                             │
        └─────────────┬───────────────┘
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

- **Backend:** Python 3.9, FastAPI, [Basic Pitch](https://github.com/spotify/basic-pitch) (ML audio→MIDI, used for both RH melody and LH harmony transcription), [Demucs](https://github.com/facebookresearch/demucs) (ML stem separation, Spec 2 only), music21, librosa, yt-dlp, spotipy, pytest.
- **Frontend:** React 18 + Vite + TypeScript, axios, [OpenSheetMusicDisplay](https://opensheetmusicdisplay.org/), html5-qrcode.

## Running it

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

YouTube-link ingestion requires `ffmpeg` to be installed and on `PATH` (used by
yt-dlp to extract audio); without it, YouTube-link and Spotify-link input will
fail.

The API listens on `http://localhost:8000`. Rendered scores and source
audio are written under `backend/storage/{song_id}/` (git-ignored, created
at runtime).

Spotify-link input additionally requires a Spotify Developer Dashboard app:

```bash
export SPOTIFY_CLIENT_ID=...
export SPOTIFY_CLIENT_SECRET=...
```

File-upload and YouTube-link input work without these.

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
suite. There is no automated frontend test suite for v1 — frontend
correctness is verified manually in a browser.

## API

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

Audio is capped at 10 minutes server-side. Tempo is assumed fixed at 120
BPM — no tempo detection for this pipeline.

`POST /arrange` — same input fields as `/transcribe`. Returns `202`
immediately:

```json
{ "job_id": "uuid4", "status": "processing" }
```

`GET /arrange/{job_id}` — poll for status. While running:

```json
{ "status": "separating" | "extracting_melody" | "detecting_key" | "arranging" }
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
  transcription/   Basic Pitch wrapper (audio → NoteEvents) — shared by both pipelines
  notation/        NoteEvent → grand-staff music21 Score, hand split, clef handling
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
