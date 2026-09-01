# Synthony

Synthony turns a solo piano recording into practice-ready sheet music at
three difficulty tiers — Easy, Medium, and Hard. Give it a file upload, a
YouTube link, a Spotify link, or a scanned QR code pointing at one of those
links, and it returns three MusicXML scores rendered in the browser.

This is **v1.0** — Spec 1 of the project: a complete, working pipeline for
audio that already contains a solo piano performance (see
[`docs/superpowers/specs/2026-08-31-solo-piano-pipeline-design.md`](docs/superpowers/specs/2026-08-31-solo-piano-pipeline-design.md)
for the full design). Source separation for arbitrary mixed-audio songs
(vocals, drums, etc.) is out of scope for this version.

## How it works

```
Input (file upload | YouTube link | Spotify link | QR-scanned link)
        │
        ▼
Ingestion — normalizes any input source to a local WAV/MP3
        │
        ▼
Transcription — Basic Pitch: audio → raw MIDI (polyphonic)
        │
        ▼
Notation — MIDI → music21 grand-staff Score
  (melody-aware hand split: highest simultaneous note = RH, rest = LH)
        │
        ▼
Difficulty engine — pure Score → Score transforms, three tiers
        │
        ▼
MusicXML export × 3
        │
        ▼
Frontend — Easy / Medium / Hard tabs, rendered via OpenSheetMusicDisplay
```

A single `POST /transcribe` endpoint drives the whole pipeline
synchronously: the request blocks until all three MusicXML variants exist
on disk.

## Stack

- **Backend:** Python 3.9, FastAPI, [Basic Pitch](https://github.com/spotify/basic-pitch) (ML audio→MIDI), music21, librosa, yt-dlp, spotipy, pytest.
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

Requires Node 18+ (Vite 5). Open the printed URL, then upload a short solo
piano recording, paste a YouTube/Spotify link, or scan a QR code — three
tabs (Easy/Medium/Hard) appear once transcription completes.

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
BPM for v1 — tempo detection is out of scope.

## Project layout

```
backend/app/
  ingestion/       file upload, YouTube download, Spotify resolution
  transcription/   Basic Pitch wrapper (audio → NoteEvents)
  notation/        NoteEvent → grand-staff music21 Score, hand split
  difficulty/       easy.py / medium.py / hard.py — pure Score → Score
  export.py        Score → MusicXML
  storage.py       song IDs, storage directories, metadata
  main.py          POST /transcribe wiring

frontend/src/
  api/             typed client for POST /transcribe
  components/      UploadForm, QrScanButton, ScoreViewer, DifficultyTabs
  App.tsx          top-level flow: upload/scan → tabs
```
