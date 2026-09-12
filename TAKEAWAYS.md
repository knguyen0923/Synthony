# Building Synthony — Project Takeaways

A retrospective on building Synthony: an app that turns audio — a file
upload, a YouTube link, a Spotify link, or a QR-scanned link — into
practice-ready piano sheet music at three difficulty tiers. Built solo,
2026-08-31 to 2026-09-11 (105 commits, 5 active build days), from empty
repo to two working end-to-end transcription pipelines with a real-audio
verification harness behind them.

## What it does

Synthony actually solves two different problems that look similar from
the outside but need completely different machinery:

- **A solo piano recording already has a piano part in it.** Spec 1
  transcribes it, note-perfect as possible, then simplifies it down into
  Easy/Medium/Hard tiers.
- **A full song (vocals, drums, bass, whatever else) has no piano part at
  all.** Spec 2 has to *invent* one: separate the mix into stems, pull a
  melody line out of the vocals, and build a genuine two-hand
  transcription of the harmonic accompaniment out of the rest.

Keeping those as two separately-selected pipelines — rather than trying
to force one model to handle both — was the load-bearing decision the
whole project sits on. Both converge on the same shared grand-staff
builder and the same pure difficulty engine, so nothing downstream of
"produce two `music21` `Part`s" ever had to be duplicated.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Solo-piano transcription | `piano_transcription_inference` (ByteDance, MAESTRO-trained) | Swapped in for Spec 1 only after a real-audio eval against Basic Pitch — onset+offset F1 went from 0.185 to 0.893 on the same clip |
| Vocal/harmony transcription | Basic Pitch (Spotify) | Kept deliberately for Spec 2's RH/LH, after evaluating and rejecting MT3 as a replacement (unmaintained in practice, 2-3 orders of magnitude slower on CPU, and redundant once Demucs has already separated the instruments) |
| Stem separation | Demucs | Self-hosted; a Phase-0 spike judged its vocal/drums/bass/other split clean enough on real pop songs before any pipeline code was written |
| Tempo | madmom's neural beat tracker, with a librosa global-tempo estimate and a fixed 120 BPM as successive fallbacks | A real per-song beat map beats a single guessed BPM, but needs graceful degradation when detection is uncertain |
| Notation | music21 (9.7+) | Grand-staff `Score` construction, MusicXML export, and (as of this project's last commits) real sustain-pedal `PedalMark` spanners instead of discarding that signal |
| Hand-splitting | Custom continuity-aware DP algorithm | Physical hand span, pitch continuity, and hand-crossing/switching penalties — not a naive "highest note = right hand" rule |
| Difficulty engine | Pure Python `Score → Score` transforms (quantize density, narrow register) | Deterministic and independently unit-testable, no ML anywhere in this step — the one place in the pipeline where "exactly right" matters more than "probably right" |
| Backend | FastAPI, Python 3.11 | Sync `/transcribe`, async `/arrange` via `BackgroundTasks` — no Celery/Redis needed at personal-project scale |
| Frontend | React 18 + Vite + TypeScript, OpenSheetMusicDisplay | Renders MusicXML straight in the browser, one tab per difficulty tier |
| Testing | pytest, TDD throughout | 227 tests, plus a separate real-audio verification harness (below) that unit tests alone can't replace |
| Hosting | None yet — personal/local only | A deliberate scope cut, not an oversight; see "What's next" |

## Architecture

```
Input (file upload | YouTube link | Spotify link | QR-scanned link)
        │
        ▼
Ingestion — shared by both pipelines
        │
        ├─────────────────────────────────┐
        ▼ (Solo piano recording)          ▼ (Any song)
Piano-specific transcription          Demucs stem separation
        │                                     │
Real beat-map tempo detection          ├─► Basic Pitch (vocals) → RH melody
        │                                     │
Continuity-aware DP hand split         └─► Basic Pitch (bass+other),
        │                                     capped polyphony → LH
        │                              chroma-based key/tempo detection
        │                                     │
        └─────────────────┬───────────────────┘
                           ▼
       build_grand_staff_score(RH, LH) — shared by both pipelines
                           │
       Difficulty engine — pure Score transforms derive Easy/Medium
       from one rich Hard base, for both hands, both pipelines
                           │
                           ▼
                MusicXML export × 3
                           │
                           ▼
     Frontend — Easy / Medium / Hard tabs, rendered via OpenSheetMusicDisplay
```

## What I actually learned, by area

### This is a "does it sound right" product, not a "does it pass" product

Unit tests on 2-second synthetic sine-wave fixtures repeatedly missed
real bugs: a MusicXML export crash that only showed up on irregular
real chord timings, tempo-relative threshold bugs that only misfired at
certain real BPMs, a melody-extraction octave artifact, a voice-count
rounding overshoot. None of those had a synthetic test case that would
have caught them — they only surfaced from running the actual pipeline
against actual songs and inspecting (or listening to) the output. The
whole project ended up running on a standing rule: after any change to
the arrangement/transcription pipeline, re-run a fixed real-audio corpus
(one solo piano recording, three real pop songs) before considering the
change done, not just the pytest suite.

### Metrics can actively mislead if you don't chase the root cause

Adding the real beat-map tempo fix caused a large, alarming-looking note
count drop. It would have been easy to assume that meant lost data. It
didn't — a controlled, order-reversed same-process test traced it to the
beat map correctly consolidating near-duplicate detections that the old
fixed-tempo grid had artificially spread apart. The number moving is not
the same thing as the number being wrong; you have to trace *why* before
trusting either direction.

### A delegated implementation's own tests aren't enough

A hand-splitting algorithm, built by a dispatched agent with its own
fresh test suite, shipped with a real tuning bug (a consolidation penalty
cheap enough that it let one wrong bundled assignment persist across
several onsets). The agent's own new tests never caught it. It only
surfaced the moment the module was integrated against this repo's
*existing* test suite. Lesson kept for the rest of the project:
integrate any delegated module through the pre-existing tests before
trusting it, never just the delegate's own.

### Root-cause the symptom, don't just cap it

A "too many simultaneous notes piled up in one hand" bug was originally
fixed by capping the max voice count after the fact — a reasonable patch,
but not the real fix. The actual cause was that a piano transcription
model's note *offset* reflects acoustic/pedal decay, not when the key was
actually released, so a sustained pedal was pinning many notes' written
durations to the same late release instant. The real fix, done later in
the project once the prerequisite music21 upgrade landed, was to notate
the pedal event itself (`PedalMark` spanners) instead of letting decay
silently inflate every note's duration underneath it — using signal the
transcription model was producing all along and had simply been
discarded.

### Deliberately not swapping something is as important a decision as swapping it

Spec 2's left hand stayed on Basic Pitch even after a piano-specific
model proved dramatically better for Spec 1's solo-piano case. MT3 was
evaluated as a replacement and rejected on evidence (unmaintained in
practice, far slower on CPU, and redundant work given Demucs had already
separated the instruments). Not every "better model exists" is worth
acting on — the right question is whether it's better *for this specific
subtask*, not better in general.

### Infrastructure has its own gotchas, independent of the ML

- madmom (an unmaintained-since-~2022 dependency needed for real beat
  tracking) doesn't import on Python 3.10+ from its last PyPI release at
  all — the fix existed only on its GitHub main branch, at a commit that
  had to be pinned and installed with build isolation off, which itself
  required numpy/scipy/Cython/mido to already be present first.
- A stale backend process from before a Python version migration can sit
  on the same dev port a fresh one expects, silently serving old
  behavior — worth a `ps -p <pid> -o command` check on anything already
  listening before trusting it's current.
- When the usual browser-automation path wasn't available for a
  rendering-verification pass, a scratch Playwright+Chromium setup
  substituted in — the verification a change needs shouldn't depend on
  exactly one tool being available.

### Working with an AI coding assistant deliberately

- **Spec first, code second.** Non-trivial pipeline changes got a
  written design doc (`docs/superpowers/specs/`) before implementation —
  scope and edge cases get decided on purpose, not discovered mid-build.
- **Verify by listening, not by trusting the harness.** Automated metrics
  guided *where* to look, but tuning decisions (a Basic Pitch
  `minimum_note_length` change, several pipeline-stage changes) were only
  actually confirmed once a human listened to the real audio — mixed or
  inconclusive metrics were treated as "needs an ear," not "good enough."
- **Draw a hard line between reversible and not.** Local edits, tests,
  and commits happened freely; nothing here ever touched a production or
  live environment — this project's own working rule going in was the
  same instruction any assistant operates under: read from anywhere,
  write only to non-production. That boundary is what made fast local
  iteration possible without a second thought about blast radius.

## By the numbers

- **105 commits**, empty repo to two complete pipelines, across 5 active
  build days spanning 2026-08-31 to 2026-09-11
- **227 automated tests**, 3,096 lines of test code vs. 2,160 lines of
  backend source (more test code than implementation — a deliberate TDD
  habit, not an accident)
- **2 full pipelines** (solo-piano transcription, any-song arrangement),
  each producing **3 difficulty tiers**, converging on one shared
  grand-staff builder and one shared difficulty engine
- **4-song real-audio verification corpus** (one solo piano recording,
  three real full songs) re-run before/after every pipeline-quality
  change, not just the unit test suite
- **$0 hosting** — not because it's free-tier deployed, but because it
  isn't deployed anywhere yet; a personal/local project by explicit
  choice, not by omission

## What's next

- **Production hardening**, scoped to what a personal/demo project
  actually needs rather than public-service infrastructure: CI running
  the existing test suite on push, a Dockerfile/local-run story, basic
  structured logging (today it's bare `try`/`except`), and a concurrency
  guardrail so heavy ML jobs can't accidentally exhaust one machine. No
  auth, no rate limiting, no distributed job queue — those only start
  mattering if this ever stops being personal-use.
- **Broadening past pop/rock** — instrumentals, rap, orchestral, and
  multi-melody songs are explicitly out of scope for the current
  arrangement engine, deferred on purpose until the pop/rock case was
  solid rather than half-solving a harder problem first.
- **A few explicitly-parked, not-forgotten items**: distinguishing
  multiple simultaneous instruments within Demucs's catch-all "other"
  stem is a real quality ceiling with no clean fix available yet, and any
  further LH onset-cleanup work is intentionally on hold unless listening
  actually surfaces it as a problem, rather than fixed pre-emptively.
