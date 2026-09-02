# Synthony — Spec 2: Any-Song Piano Arrangement

## Status (updated 2026-09-02)

Phases 0-4 are complete and merged into `spec-1-solo-piano-pipeline`
(`POST /arrange` is live). Phase 5 (quality iteration by ear) is
in progress. Phase 6 (broaden beyond pop/rock) hasn't started.

**One decision below was reversed since this doc was written**: the
Key Decisions Log's "Chord-symbol arrangement, not stem-transcription
reuse" call — LH is no longer generated from detected chord symbols via
a rule-based pattern engine. It's now a **real transcription** of the
bass+other stem mix (Basic Pitch, same tool already used for RH melody),
mirroring how RH always worked, with Easy/Medium mechanically simplified
from that one rich transcription. See
[`2026-09-02-lh-true-transcription-design.md`](2026-09-02-lh-true-transcription-design.md)
for the full rationale and design — this doc's Architecture diagram,
Goals' arrangement bullet, Phase 3, "Arrangement engine" component, and
the API Contract's `detecting_chords` status string below are all
superseded by it. Everything else in this doc (stem separation, melody
extraction, async job infra, storage/frontend contract) still describes
the current system accurately. The rest of this document is left as
originally written, as the historical record of the original design.

## Context

Spec 1 (v1.0) transcribes audio that already contains a solo piano
performance. It cannot help with the far more common case: a song that
has no isolated piano at all — vocals, guitar, drums, bass, all mixed
together. Spec 2 adds a second pipeline, selected explicitly by the user,
that takes **any song** and produces an original two-hand piano
arrangement: melody extracted as the right hand, a newly composed
accompaniment as the left hand.

This is a genuinely different problem from Spec 1. Spec 1 simplifies an
existing piano performance; Spec 2 *invents* a piano part for a song that
never had one. It needs source separation (to isolate a clean melody and
harmony), a melody line, harmonic analysis (chord recognition), and a new
rule-based arrangement engine to turn chords into a playable LH — none of
which Spec 1 required.

Spec 2 targets **pop/rock songs with a clear lead vocal melody and
chordal instrumental backing** first (the common case). Fully general
input (instrumentals, rap, orchestral, genres with no clear melody or
fixed chord grid) is deliberately deferred to a later spec, once this
narrower case is solid.

## Goals

- Add an "Any song" input mode, alongside the existing "Solo piano
  recording" mode, that accepts the same input types (file / YouTube /
  Spotify / QR) Spec 1 already supports.
- Separate the mix into stems, extract a monophonic melody line from the
  vocal stem, and build the RH part from it.
- Detect a chord-per-beat sequence from the harmony stems and generate an
  LH accompaniment from it via deterministic, pure Score-transform rules
  (same philosophy as the existing difficulty engine) — not by
  transcribing and reusing raw separated-instrument audio.
- Feed the resulting grand-staff Score into the **existing, unchanged**
  difficulty engine and MusicXML export.
- Move processing to an async job (submit → poll) so a multi-minute
  separation+analysis run doesn't hold open a single blocking HTTP
  request the way Spec 1's `/transcribe` does.
- Validated by ear against real songs — no automated audio-quality
  metrics for v1.

## Non-Goals (Out of Scope for Spec 2)

- Genres without a clear lead vocal melody or stable chord grid
  (instrumentals, rap, orchestral, most electronic music) — a later spec.
- Multiple simultaneous melodic lines (e.g. call-and-response, duet
  vocals) — single lead melody only.
- User-editable/correctable arrangements (fixing a wrong chord, moving a
  note) — output is what the pipeline produces.
- Re-architecting Spec 1's solo-piano pipeline — it stays as-is; Spec 2
  is an additional, separately-selected pipeline.
- Real-time/streaming processing — still a submit-and-wait job, just
  asynchronous instead of a blocking request.

## Architecture

```
Full song (file upload | YouTube link | Spotify link | QR-scanned link)
        │
        ▼
Ingestion — reused as-is from Spec 1
        │
        ▼
Stem separation (NEW) — vocals / drums / bass / other
        │
        ├──► Melody extraction (NEW) — Basic Pitch (existing tool) on the
        │      vocal stem → reduce polyphonic output to a single
        │      monophonic top line → RH Part
        │
        └──► Chord recognition (NEW) — chroma/template matching over the
               bass+other stems → chord-per-beat/bar sequence
                     │
                     ▼
               Arrangement engine (NEW) — chord sequence → LH Part,
               pure deterministic transform, pattern varies by
               difficulty tier (root notes / block chords / arpeggios)
        │
        ▼
build_grand_staff_score(RH, LH) — reused as-is from Spec 1's notation module
        │
        ▼
difficulty/engine.py — reused as-is (operates on any Score, not
specific to how the notes were produced)
        │
        ▼
MusicXML export × 3 — reused as-is
```

Everything below "Stem separation" that isn't marked NEW is Spec 1 code,
unmodified — the two pipelines diverge only at ingestion's output and
reconverge at the grand-staff `Score`.

## Phased Roadmap

- **Phase 0 — Spike (~1 week).** Validate the two riskiest unknowns
  before writing any pipeline code: (a) does a self-hosted separator
  (e.g. Demucs) isolate vocals and harmony cleanly enough on real pop
  songs to be usable, and (b) does a chroma-based chord recognizer
  produce musically sane chord sequences on the separated harmony
  stems. Judged by ear against a handful of real songs. No code kept —
  a go/no-go recommendation, and a choice of separation/chord-detection
  libraries to build on.
- **Phase 1 — Separation + melody (RH).** Integrate stem separation into
  a new ingestion path. Run Basic Pitch on the vocal stem, reduce its
  polyphonic output to one melody line per moment (highest-confidence
  note, or highest-pitched — exact heuristic tuned by ear, akin to Spec
  1's melody-aware hand split), build the RH `Part`. Independently
  testable/listenable as melody-only piano before any LH work exists.
- **Phase 2 — Chord recognition.** Chroma/template-based chord detection
  over the harmony stems (bass + other), quantized to a chord-per-beat
  or chord-per-bar sequence with a detected key/tempo grid.
- **Phase 3 — Arrangement engine (LH).** Pure, deterministic
  `chord sequence -> Part` transforms — no ML, no training data. Pattern
  varies by difficulty tier: root notes only for Easy, block chords for
  Medium, arpeggiated/Alberti-bass patterns for Hard. Structured the
  same way as the existing `difficulty/` module: small, independently
  unit-testable functions.
- **Phase 4 — Async job infra + UI integration.** Background job
  processing (`POST /arrange` returns a job id immediately; `GET
  /arrange/{job_id}` reports status and, when done, the same
  `TranscribeResponse`-shaped result Spec 1 already returns), a progress
  indicator in the UI, and the "Any song" input-mode toggle alongside
  today's "Solo piano recording" mode.
- **Phase 5 — Quality iteration on pop/rock.** Run real songs end-to-end,
  tune separation/chord/arrangement parameters by ear until arrangements
  are genuinely good, on the pop/rock case this spec targets.
- **Phase 6 (later, separate spec) — Broaden beyond pop/rock.**
  Instrumentals, no-clear-melody genres, multi-melody songs, etc. —
  explicitly deferred until Phase 5 is solid; not scoped further here.

Phases 0–3 can be built and validated independently of each other before
any UI work — each phase's output (isolated stems, a melody line, a
chord sequence, an LH part) is separately inspectable/listenable, so
quality problems surface early rather than only at the end of the full
pipeline.

## New Components

**Stem separation** (`ingestion/` or a new `separation/` module) — takes
the same normalized WAV/MP3 Spec 1's ingestion already produces, runs a
self-hosted separator, and returns paths to isolated vocal/drums/bass/
other stems. Library choice (Demucs vs. alternatives) is a Phase 0
output, not decided here.

**Melody extraction** (new module) — runs the existing Basic Pitch
wrapper (`transcription/audio_to_midi.py`, unmodified) against the vocal
stem, then reduces its polyphonic output to a single line: at each
moment, pick one note (heuristic TBD in Phase 1 — likely highest-pitched
or highest-confidence) to represent the sung melody, discarding the rest.
This is a new reduction step; Basic Pitch itself is reused unmodified.

**Chord recognition** (new module) — chroma-feature extraction (e.g. via
`librosa`, already a dependency) plus template matching against a fixed
set of chord qualities (major/minor/7th/etc.), quantized to a
beat/bar grid. No ML model, no training data — the same "deterministic,
inspectable" bias as the rest of this codebase.

**Arrangement engine** (new `arrangement/` module, parallel to
`difficulty/`) — pure `chord sequence -> Part` functions, one pattern
style per difficulty tier. Explicitly modeled on `difficulty/easy.py`
/ `medium.py` / `hard.py`'s existing pattern of small, hand-testable
pure transforms.

## API Contract

**`POST /arrange`** — multipart form, same input fields as `/transcribe`
(`audio_file` / `youtube_url` / `spotify_url`), routing to the Spec 2
pipeline instead of Spec 1's.

Response `202`:
```json
{ "job_id": "uuid", "status": "processing" }
```

**`GET /arrange/{job_id}`** — poll for status.

Response `200` while running:
```json
{ "status": "separating" | "extracting_melody" | "detecting_chords" | "arranging" }
```

Response `200` when done — same shape `/transcribe` already returns, so
the frontend's existing result view (`DifficultyTabs`, `ScoreViewer`)
needs no changes to render it:
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

**Error responses** — job status becomes `"failed"` with a `detail`
message (separation failure, no clear melody detected, no chords
detected) rather than an HTTP error status, since the failure is
discovered asynchronously after the initial `202`.

Job storage/lifecycle (in-memory vs. persisted, cleanup policy) is left
for the Phase 4 implementation plan — out of scope for this design doc
beyond the endpoint contract above.

## Storage

Extends Spec 1's `backend/storage/{song_id}/` layout — same directory,
same `easy.musicxml` / `medium.musicxml` / `hard.musicxml` / MusicXML
outputs, so the existing `/songs` history endpoints (list/get/delete)
work for Spec 2 songs without modification. Additional intermediate
artifacts (separated stems, detected chord sequence) may be written
alongside for debugging but are not part of the public API.

`metadata.json` gains a field distinguishing which pipeline produced the
song (`"pipeline": "transcribe" | "arrange"`), so History can label
entries accordingly.

## Frontend

1. Input screen gains a second mode alongside "Solo piano recording":
   "Any song" — same three entry points (file/link/QR), routed to
   `POST /arrange` instead of `POST /transcribe`.
2. On submit: poll `GET /arrange/{job_id}` and show a progress indicator
   reflecting the current stage (separating → extracting melody →
   detecting chords → arranging), instead of Spec 1's single spinner.
3. On success: identical result view to Spec 1 (`DifficultyTabs` /
   `ScoreViewer`) — no changes needed there, since the response shape is
   the same.
4. On failure: inline message using the job's `detail` field.

## Testing Strategy

- **Melody extraction / chord recognition**: unit tests against small
  synthetic/fixture audio with known expected output (a known melody
  line, a known chord progression), loosely asserted — same spirit as
  Spec 1's Basic Pitch wrapper tests.
- **Arrangement engine**: the highest-value test surface, same as Spec
  1's difficulty engine — pure `chord sequence -> Part` functions, unit
  tested with hand-crafted chord sequences and exact expected output.
- **Stem separation**: integration-style test against a short fixture
  with a known instrument mix, checked loosely (e.g. "a vocal stem file
  is produced and is not silent").
- **API layer**: integration tests against the full async job lifecycle
  — submit, poll through status transitions, assert final result shape
  matches `/transcribe`'s.
- **End-to-end quality**: manual, by-ear validation against real songs
  per phase (per the Quality Bar decision below) — not automated.

## Key Decisions Log

- **Full general scope, phased**: Spec 2 targets "any song → piano
  arrangement" as the eventual goal, but Phase 0–5 scope only pop/rock
  songs with a clear lead vocal melody and chordal backing. Fully
  general genre support is a later spec (Phase 6+), not blocking this
  one.
- **User picks the input mode** ("Solo piano recording" vs. "Any song")
  rather than auto-detecting which pipeline a song needs — simpler,
  predictable, no misdetection risk.
- **Chord-symbol arrangement, not stem-transcription reuse**: the LH is
  generated by a new rule-based arrangement engine from detected chord
  symbols, not by running Basic Pitch on the separated harmony stems and
  reusing its raw output directly. More new engineering than the
  reuse-heavy alternative, chosen for cleaner, more controllable,
  per-tier LH output.
- **Async job (`POST /arrange` + polling)**, not a blocking request like
  Spec 1's `/transcribe` — stem separation on CPU can take
  real-time-or-slower, making a multi-minute blocking HTTP request
  impractical.
- **Deterministic, non-ML arrangement and chord recognition** — chroma/
  template matching and pure rule-based transforms, consistent with the
  rest of the codebase's testable, inspectable style. No generative
  model, no training data.
- **Quality bar is subjective**: judged by ear/by playing against real
  songs, same validation approach used for Spec 1 — no automated
  audio-quality metrics for v1.
- **Reuses Spec 1's difficulty engine, notation's `build_grand_staff_score`,
  and MusicXML export unchanged** — Spec 2 only replaces how the RH and
  LH `Part`s are produced, not anything downstream of the grand-staff
  `Score`.
