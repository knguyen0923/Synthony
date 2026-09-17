# Building Synthony — Project Takeaways

A retrospective on building Synthony: an app that turns audio — a file
upload, a YouTube link, a Spotify link, or a QR-scanned link — into
practice-ready piano sheet music at three difficulty tiers. Built solo,
2026-08-31 to 2026-09-12 (167 commits, 6 active build days), from empty
repo to two working end-to-end transcription pipelines, a real-audio
verification harness, CI, structured logging, a concurrency guardrail, a
Docker local-run story, a discovery-sweep bug-fix pass, and a
production-readiness pass on top.

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
| Testing | pytest, TDD throughout | 273 tests, plus a separate real-audio verification harness (below) that unit tests alone can't replace |
| CI | GitHub Actions | Backend suite + frontend build/lint on every push to `main` and every PR |
| Concurrency | A `threading.BoundedSemaphore`-based job-slot limiter | Caps simultaneous heavy ML jobs (`MAX_CONCURRENT_JOBS`, default 2) — no Celery/Redis needed at this scale |
| Hosting | None live — Docker Compose for local runs only | A deliberate scope cut, not an oversight; see "What's next" |

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

### A plausible root-cause hypothesis still needs direct verification

Mid-investigation into Big Rock's "plays too slow" complaint, once a
half-time tempo-detection misread was confirmed by ear, the natural next
hypothesis was that the beat tracker was being fed an ambiguous signal —
it ran on a bass+other "harmony" mix, and Demucs already separates a
`drums` stem (unused anywhere in the codebase) that should carry a far
clearer, less ambiguous beat signal. That reasoning was sound but wrong:
running the same detector directly on Big Rock's real isolated drums
stem still misread it at ~107 BPM, identical to the harmony-mix result.
The half-time ambiguity turned out to live in the backbeat pattern's own
accent structure (a driving rock backbeat's strongest hits *are* at the
half-time rate), not in cross-instrument interference — isolating the
drums doesn't remove an ambiguity that isn't about instrument bleed in
the first place. The stem-routing change shipped anyway (harmless, fully
tested), but the actual fix still needs the originally-designed
onset-midpoint correction heuristic. Caught only because the "confirm
against real audio" habit extended to the fix itself, not just the bug.

### A measured accuracy number beats "seems about as good as before"

The quality harness (`backend/scripts/quality_harness/`) diffs objective
metrics run-over-run — note count, voice count, pitch range — but it
never checked correctness against a known-right answer, only "did this
change move the numbers." A portfolio review flagged the gap: pull a
handful of MAESTRO clips (piano recordings paired with ground-truth
MIDI — the same corpus `piano_transcription_inference` was trained on),
run them through Spec 1's transcription function directly, and score
onset+pitch precision/recall/F1 against ground truth with `mir_eval`
(the standard MIR research library, not a hand-rolled matcher). The
harder part turned out to be getting the 5 test-split clips onto disk at
all: MAESTRO's audio only ships inside one ~108GB zip, and neither GCS
nor Hugging Face serves its individual extracted members as separate
URLs (confirmed directly — per-file URLs 404). `remotezip` reads the
zip's central directory and fetches only the requested member's bytes
via HTTP range requests, verified live before it went in a plan: an
~85MB member in ~5 seconds, not the time to pull 108GB. The real result,
run against 5 held-out test-split clips spanning 5 composers: aggregate
precision 0.977, recall 0.935, F1 0.956 over 7,707 ground-truth notes —
close to, but measurably below, the checkpoint's own reported training
F1 of 0.9677 (the number embedded in its filename), with the model
consistently dropping more true notes than it hallucinates (recall
trails precision on every clip, most on the densest/most virtuosic one).
That gap between "the model's own reported number" and "what it actually
does on held-out audio run through this exact pipeline" is precisely
what a diff-only harness can never surface.

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

### Balanced metrics can still be the wrong answer

A follow-up bug in the hand-splitting algorithm (it forced every "lone
note" onset to the right hand unconditionally — correct for solo piano,
wrong for multi-instrument input) got a real, independently-verified fix.
But real-audio verification on the fix surfaced a second problem no
metric had flagged: the fixed algorithm produced a well-balanced RH/LH
note count on a rock instrumental (1169/29 → 670/540) yet sounded
"incoherent/scattered" by ear. Sweeping the tuning parameter against the
real note stream confirmed balance and flicker were in direct
opposition — a value strong enough to suppress the flicker just
recreated the original bug. The actual fix was structural, not a tuning
number: transcribe the bass and "other" stems *separately* (bass → LH,
other → RH) instead of mixing them into one signal and re-splitting by
continuity, since continuity-based splitting assumes one performer's two
hands, not two different instruments interleaved in time. Lesson: when a
metric and your ear disagree, trust the ear and go looking for a
structural cause, not a better-tuned constant.

### A discovery sweep is worth doing even with no new feature to build

Once both pipelines were stable, a dedicated pass ran a backend
`/code-review`, a backend error-handling audit, and a frontend
`/code-review` — not chasing any specific bug, just looking. It found
real, previously-unnoticed gaps: Spotify ingestion was unconditionally
broken in the default unconfigured state (`SpotifyOauthError` isn't a
subclass of the exception type the existing handler caught, confirmed by
direct execution, not just reading the code); a non-audio/corrupt upload
surfaced as a raw 500 instead of a clean 422; several React components
had real lifecycle bugs (a failed camera permission left a scan button
permanently disabled, a file input never reset after a failed upload,
state updates could fire after unmount). None of these were regressions
from a specific change — they'd been latent since whenever that code was
first written. Worth scheduling this kind of sweep periodically, not just
reacting to bugs the user happens to notice.

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

### Production hardening surfaced its own class of lessons

Once the pipelines were solid, a separate pass added CI, structured
logging, a concurrency guardrail, and Docker support — deliberately scoped
to what a personal/demo project needs, not public-service infrastructure
(no auth, no rate limiting beyond the concurrency cap, no distributed job
queue). Running this as a plan with independent task-level review, plus
one broad whole-branch review at the end, caught things a single pass
wouldn't have:

- **A review that reproduces a claim beats a review that reads it.** A
  fix for "Docker doesn't pick up Spotify credentials from `backend/.env`"
  added an `env_file` directive that looked correct on paper. The
  re-review didn't just read the diff — it ran `docker compose config`
  against a real test `.env` and found the fix was completely inert: a
  pre-existing `environment:` block in the same file silently overrides
  `env_file` for identical keys in Docker Compose's precedence rules. The
  bug wasn't in unfamiliar code; it was in a two-line YAML file, and it
  still needed empirical reproduction to catch.
- **Real infrastructure findings don't always get a same-session fix, and
  that's fine if it's said out loud.** Two genuine, evidence-backed gaps
  ended this pass documented-but-unfixed rather than patched: the backend
  Docker image doesn't build natively on Apple Silicon at all (a `demucs`
  transitive dependency, `sphn`, ships no `linux/aarch64` wheel — confirmed
  by testing both an arm64 build and an emulated amd64 build side by side),
  and the docker-compose fix above. Attempting a real fix for the former
  (a Rust toolchain so `sphn` builds from source) would have needed a slow,
  uncertain verification cycle for the least-critical task in the plan;
  the honest move was a clear comment explaining the gap and a workaround,
  not a confident-looking but unverified patch.
- **A plan can specify a broken test, and a good implementer will catch
  it, not just follow it.** One task's own written instructions told an
  implementer to monkeypatch a semaphore reference on the wrong module.
  Patching it there would have made the test pass without actually testing
  anything (the object being patched was never read at runtime). Catching
  this required the implementer to trace *where* a value is actually
  looked up at call time, not just where a plan says to patch it — the
  written plan is an argument, not a substitute for reading the code.

## By the numbers

- **167 commits**, empty repo to two complete pipelines plus a hardening
  pass, a discovery-sweep bug-fix pass, a production-readiness pass, and a
  follow-up event-loop-blocking fix, across 6 active build days spanning
  2026-08-31 to 2026-09-12
- **285 automated backend tests** (plus a separate frontend Vitest suite),
  4,339 lines of backend test code vs. 2,556 lines of backend source
  (more test code than implementation — a deliberate TDD habit, not an
  accident)
- **A measured ground-truth transcription accuracy number, for the first
  time**: 0.956 aggregate F1 (precision 0.977, recall 0.935) against 5
  held-out MAESTRO test-split clips (7,707 ground-truth notes), replacing
  "seems about as good as before" with an actual number
- **2 full pipelines** (solo-piano transcription, any-song arrangement),
  each producing **3 difficulty tiers**, converging on one shared
  grand-staff builder and one shared difficulty engine
- **4-song real-audio verification corpus** (one solo piano recording,
  three real full songs) re-run before/after every pipeline-quality
  change, not just the unit test suite
- **$0 hosting** — not because it's free-tier deployed, but because it
  isn't deployed anywhere yet; a personal/local project by explicit
  choice, not by omission. A `docker compose up` local-run story exists
  and builds natively on both linux/amd64 and arm64 (Apple Silicon)

## What's next

Resolved since the hardening pass above: CI now runs the frontend Vitest
suite (not just build/lint) on every push; the docker-compose
`env_file`/`environment:` key-shadowing bug is fixed, so `backend/.env`
credentials actually reach the container; and native arm64 Docker builds
work (a Rust/maturin toolchain builds `sphn`, the `demucs` transitive
dependency with no `linux/aarch64` wheel, from source).

The instrumental (no-vocal-melody) arrangement path is explicitly
**shelved** — after hearing the stem-split fix's output, the user wasn't
sure how they felt about arrange-instrumental quality overall, and the
decision was to stop investing further in it for now rather than keep
tuning an open question. A discovery-sweep bug-fix pass (ingestion error
handling, one observability gap, six frontend lifecycle bugs) shipped
instead — see the lessons above. The "production readiness" pass that
followed is now done: it shipped stem-directory cleanup (both going
forward, via the arrange pipeline deleting `stems/` right after a
successful run, and a one-time sweep of the ~55 pre-existing song
directories that predated that fix), a `/health` endpoint reporting
ffmpeg/piano-model status plus a startup warning if either's missing,
rotating file logging alongside stdout, and a `backend/setup.sh` script
to mechanize the venv setup dance. A closing whole-branch audit sweep on
top of that caught a handful of doc-staleness and robustness findings
(this file's own stale counts among them) — fixed in one final wave
rather than left for a second round.

- **Resolved**: a ground-truth transcription accuracy eval now exists
  (`backend/scripts/ground_truth_eval/`) — the first of the 5-item
  2026-09-16 portfolio-review backlog (see `RESUME.md`). Aggregate
  precision/recall/F1 against 5 real MAESTRO test-split clips: 0.977 /
  0.935 / 0.956 over 7,707 ground-truth notes. See the lesson above.
  Unblocks the next backlog item (validating difficulty tiers against
  real human judgment, which depends on this eval existing first).
- **Resolved**: `/transcribe`'s pipeline no longer blocks the event loop —
  the CPU-bound half (transcription, notation, export) now runs via
  `run_in_threadpool`, so the `MAX_CONCURRENT_JOBS` guardrail is reachable
  for the first time (a second `/transcribe` couldn't even get scheduled
  before). Caught its own plan defect along the way: the first version of
  the regression test reused this test file's shared, non-context-managed
  `TestClient`, which turned out to never share one event-loop portal
  across requests — it would have passed even against the broken code.
  Verified empirically (in a throwaway worktree, both by the implementer
  and independently by the final reviewer) that the corrected test fails
  without the fix and passes with it, before trusting it.
- **Resolved**: the *ingestion* step (YouTube/Spotify download via
  yt-dlp, `librosa.get_duration`) no longer blocks the event loop —
  `_ingest_and_validate_duration` (shared by `/transcribe` and
  `/arrange`) now runs both blocking calls via `run_in_threadpool`, the
  same fix shape as the pipeline fix above. Verified with the same
  technique as that fix's own regression test: a mocked slow `ingest()`
  call plus a concurrent `/health` request through one shared
  `TestClient` portal, confirming `/health` stays fast while ingestion
  is "running."
- **Resolved**: exported MusicXML now carries an explicit tempo
  marking. Confirmed by direct execution during the Big Rock tempo
  investigation that no arrangement Synthony had ever exported carried
  one at all — playback speed was entirely up to whatever default the
  importing software assumed, decoupled from the tempo actually
  detected in the source audio. `BeatMap.bpm_at()` already existed for
  exactly this ("intended for eventually annotating tempo-change
  markings in exported notation" — see `app/tempo/detect.py`); the fix
  wires it through the one shared `build_grand_staff_score()` helper
  (a `tempo_qpm` param → a music21 `MetronomeMark`) and a matching
  `get_tempo()` reader so Easy/Medium correctly carry the Hard tier's
  tempo forward, the same way `get_title()` already does. This is the
  confirmed half of the Big Rock complaint's two hypotheses.
- **Confirmed, not yet fixed**: the second hypothesis — that the
  detected tempo itself is a half-time misread — is now confirmed by
  ear (a doubled-BPM render matches the real recording's backbeat
  better than the detected-BPM render). A drums-stem-preferred routing
  change shipped and is fully tested (`has_audible_signal` +
  `run_arrange_pipeline` preferring Demucs's previously-unused `drums`
  stem over the bass+other harmony mix when it carries real signal),
  but direct verification against Big Rock's actual drums stem showed
  it doesn't fix the misread — see the lesson above. The actual fix
  (an onset-midpoint correction heuristic) is designed but not yet
  implemented; paused here per explicit user decision. See `RESUME.md`.
- **Broadening past pop/rock** — instrumentals, rap, orchestral, and
  multi-melody songs are explicitly out of scope for the current
  arrangement engine, deferred on purpose until the pop/rock case was
  solid rather than half-solving a harder problem first.
- **A few explicitly-parked, not-forgotten items**: distinguishing
  multiple simultaneous instruments within Demucs's catch-all "other"
  stem is a real quality ceiling with no clean fix available yet, and any
  further LH onset-cleanup work is intentionally on hold unless listening
  actually surfaces it as a problem, rather than fixed pre-emptively.
