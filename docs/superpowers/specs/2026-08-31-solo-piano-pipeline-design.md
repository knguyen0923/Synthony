# Synthony — Spec 1: Solo-Piano Transcription Pipeline

## Context

Synthony turns a music recording into practice-ready piano sheet music at
three difficulty tiers (Easy, Medium, Hard). The full product vision
includes generating piano arrangements from arbitrary songs (full mixed
audio with vocals, drums, etc.), but that requires source separation and
an arrangement engine — open-ended problems distinct from simplifying an
existing transcription.

This spec covers **Spec 1 only**: a complete, working pipeline for audio
that already contains a solo piano performance. It proves the full
architecture — ingestion, transcription, notation, difficulty tiering,
and rendering — end to end, on the input Basic Pitch is actually built
to handle. A future Spec 2 will add source separation and an arrangement
engine on top of this foundation (see "Out of Scope" below).

## Goals

- Accept a solo piano recording via file upload, YouTube link, or
  Spotify link (resolved via YouTube), plus a QR-code shortcut for
  entering a link.
- Transcribe it to MIDI, convert to a proper two-hand grand-staff piano
  score, and produce three difficulty variants.
- Render all three variants in the browser via OpenSheetMusicDisplay,
  one tab per tier.
- Keep the difficulty engine pure and independently testable.

## Non-Goals (Out of Scope for Spec 1)

- Source separation + arrangement-from-any-song (a mixed track with no
  piano, e.g. a pop song with vocals/guitar/drums) — this is Spec 2.
- Mic input / live listening.
- Practice mode / playback cursor sync.
- Mobile client.
- PDF export.
- Non-piano instruments or guitar tab.

## Architecture

```
Input (file upload | YouTube link | Spotify link | QR-scanned link)
        │
        ▼
Ingestion — normalizes any input source to a local WAV/MP3
  - file upload: saved as-is
  - YouTube link: audio extracted via yt-dlp
  - Spotify link: track resolved via Spotify Web API (metadata only,
    no audio) → matching video searched on YouTube → yt-dlp
        │
        ▼
audio_to_midi.py (transcription/) — Basic Pitch: audio → raw MIDI
(polyphonic, no hand/staff assignment yet)
        │
        ▼
notation/ — MIDI → music21 Score
  - melody-aware hand split (see below) → grand staff, RH treble / LH bass
        │
        ▼
difficulty/engine.py — Score → 3 variants (pure transforms, no I/O)
  - easy.py
  - medium.py
  - hard.py
        │
        ▼
MusicXML export × 3
        │
        ▼
Frontend — 3 tabs (Easy/Medium/Hard), each rendered via OpenSheetMusicDisplay
```

A single `POST /transcribe` endpoint drives the whole pipeline
synchronously — the request blocks until all three MusicXML variants are
ready. This fits local-first, single-user v1 usage; revisit if songs get
long or usage grows beyond one concurrent user.

## Ingestion

Input source is decided by which field is present in a `POST /transcribe`
multipart request; QR scanning is a frontend-only convenience that decodes
a link and feeds it into the same link field — it introduces no new
backend behavior.

- **YouTube**: downloading audio via `yt-dlp` for a local, single-user
  practice tool sits in a known ToS gray area (similar to other
  established personal-use tools). Proceeding on that basis; not
  suitable for a hosted multi-user service without revisiting.
- **Spotify**: there is no legitimate way to obtain full-track audio
  bytes from Spotify (playback is DRM-protected; the old 30-second
  preview field is deprecated for most apps). Spotify links are resolved
  to track/artist metadata via Spotify's official Web API, then matched
  against a YouTube search, and audio is pulled from that YouTube result.
  This means Spotify input can occasionally resolve to the wrong
  recording/version — acceptable for v1.
- A duration cap of **10 minutes** applies to all input sources, to keep
  the synchronous request bounded. Audio exceeding this is rejected
  (413) before transcription begins.

## Notation — Melody-Aware Hand Split

Basic Pitch outputs a flat, polyphonic stream of notes with no hand or
staff assignment. Rather than a fixed pitch threshold (e.g. "middle C and
above is RH"), hand assignment is **melody-aware**: at each moment in
time, the highest-sounding note is treated as the melodic line and always
assigned to the right hand, regardless of its absolute pitch. Every other
simultaneous note (accompaniment, harmony, bass) goes to the left hand.

This runs once, upstream of all three difficulty tiers, so the melody
stays visually and audibly contiguous in the RH at every difficulty —
including passages where the melody dips below middle C. Monophonic
passages (one note at a time) are always melody → RH. True voice-crossing
moments are rare in solo piano transcription; "highest note = melody" is
the v1 heuristic, to be refined by ear if it misfires in practice.

## Difficulty Engine

All three transforms are pure functions: `Score -> Score`, with no I/O
inside them. `difficulty/engine.py` orchestrates: takes the single
upstream (melody-split, grand-staff) Score and calls all three, returning
three independent variants.

**Easy** (`difficulty/easy.py`):
1. Inherits the melody-aware hand split from the notation stage.
2. Rhythm quantized to a quarter/eighth-note grid: for each grid slot,
   keep only the first note that starts within it; drop the rest. This
   naturally thins fast passages into something a beginner can play.
3. LH reduced to root note only, one per harmonic change.
4. Range narrowed to ~1 octave around a fixed, comfortable hand
   position. Notes outside that window are octave-shifted (preserving
   pitch class) until they land inside it — melodic contour and note
   identity are preserved, just relocated in register.
5. Accidental spelling simplified for readability via music21's spelling
   logic. **No key transposition** — pitches stay faithful to the
   original recording; only how they're notated changes.

**Medium** (`difficulty/medium.py`):
1. Inherits the same melody-aware hand split.
2. Lighter rhythm quantization than Easy (eighths / some syncopation
   allowed). Exact grid to be tuned by ear during implementation.
3. LH voicing: `chordify` the original simultaneous LH notes at each
   moment, then reduce each resulting chord to its 2–3 most structurally
   important tones (root/third/fifth), dropping doublings and
   extensions. Voicings are grounded in what was actually played, not
   inferred via harmonic/roman-numeral analysis.
4. Range window wider than Easy's, same octave-shift-to-fit approach for
   out-of-window notes.

**Hard** (`difficulty/hard.py`):
- Passthrough. Takes the melody-split, grand-staff Score as-is — no
  quantization, no voicing reduction, no range narrowing. Closest tier to
  the original transcription.

## API Contract

**`POST /transcribe`** — multipart form, exactly one of:
- `audio_file`: uploaded WAV/MP3 binary
- `youtube_url`: string
- `spotify_url`: string

Response `200`:
```json
{
  "song_id": "uuid",
  "title": "resolved or filename-derived title",
  "difficulties": {
    "easy":   { "musicxml_url": "/storage/{song_id}/easy.musicxml" },
    "medium": { "musicxml_url": "/storage/{song_id}/medium.musicxml" },
    "hard":   { "musicxml_url": "/storage/{song_id}/hard.musicxml" }
  }
}
```

MusicXML content is served as static files rather than embedded in the
JSON response, keeping the response small and letting each frontend tab
load its score independently.

**Error responses** — `4xx`/`5xx` with a `detail` message:
| Condition | Status |
|---|---|
| No pitched content detected (silence, pure percussion) | 422 |
| YouTube/Spotify resolution failure (unavailable, no search match) | 422 |
| Unsupported file type / corrupt audio | 400 |
| Audio exceeds the 10-minute duration cap | 413 |

## Storage

Local filesystem under `backend/storage/{song_id}/`, `song_id` a UUID4
generated at the start of the pipeline:
- `source.{wav,mp3}` — original or downloaded source audio
- `raw.mid` — Basic Pitch output
- `easy.musicxml`, `medium.musicxml`, `hard.musicxml`
- `metadata.json` — title, source type (upload/youtube/spotify), original
  URL if applicable, created timestamp

## Frontend

1. Input screen with three entry points: file drop/picker, a paste-a-link
   field (accepts YouTube or Spotify URLs; backend disambiguates), and a
   QR-scan button (opens the webcam, decodes via a JS QR library,
   populates the link field, auto-submits).
2. On submit: a single loading spinner for the duration of the blocking
   `POST /transcribe` call — no granular progress reporting, per the
   synchronous processing decision.
3. On success: three tabs (Easy / Medium / Hard), each an
   `OpenSheetMusicDisplay` instance loading its MusicXML from
   `/storage/{song_id}/{tier}.musicxml`.
4. On error: inline message using the response's `detail` field (e.g.
   "No pitched content detected," "Couldn't find that song on
   YouTube").

## Testing Strategy

- **Difficulty engine** (`easy.py`, `medium.py`, `hard.py`,
  `engine.py`): the highest-value test surface. Pure `Score -> Score`
  functions — unit tests build small hand-crafted `music21` Scores (a
  few measures, known notes/chords/timing) and assert exact output
  Scores. No audio, no I/O, fast and deterministic.
- **Notation stage** (melody-aware hand split): unit tests on synthetic
  note lists with known melody lines, including the voice-crossing edge
  case, asserting correct RH/LH assignment.
- **Ingestion** (file/YouTube/Spotify normalization): tests mock external
  calls (yt-dlp, Spotify API) rather than hitting real network services;
  assert each input type resolves to a local audio file path and that
  failures surface the correct error type.
- **`audio_to_midi.py`** (Basic Pitch wrapper): a couple of
  integration-style tests against a short known audio fixture, checked
  loosely (e.g. "at least N notes detected in roughly the right range")
  since third-party model output isn't hand-controllable.
- **API layer** (`POST /transcribe`): integration tests hitting the full
  pipeline with a small fixture WAV, asserting response shape and that
  all three MusicXML files are written to storage.
- **Frontend**: manual verification in-browser for v1 (upload a fixture
  song, confirm all three tabs render). No automated frontend suite
  specified for Spec 1.

## Key Decisions Log

- **Piano only** for v1 — difficulty rules and hand-splitting assume
  two-hand piano writing.
- **Spec 1 = literal transcription** of solo piano recordings, not
  arrangement from arbitrary mixed audio. Arrangement-from-any-song
  (needing source separation) is Spec 2, built after this foundation
  ships.
- **Synchronous `POST /transcribe`** rather than async job/polling, given
  local-first single-user v1 scope.
- **Grand staff, two hands** — not a single staff.
- **Melody-aware hand split** (highest note = melody = RH) at every
  tier — supersedes an earlier fixed-C4-threshold approach, which would
  have broken melodic continuity whenever a melody line dipped below
  middle C.
- **Easy tier**: keep-first-note-per-slot quantization; octave-shift for
  out-of-range notes; notation-only key simplification (no transposition).
- **Medium tier**: chord voicings derived from actual simultaneous LH
  notes (`chordify` + reduce), not inferred harmonic analysis.
- **Single unified ingestion endpoint**, not separate routes per input
  type — matches the "one top-level endpoint" convention.
- **Spotify links resolve via YouTube search** (metadata lookup only
  through Spotify's official API) since direct audio extraction from
  Spotify is not legitimately possible.
