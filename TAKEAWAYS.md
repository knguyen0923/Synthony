# Building Synthony — Project Takeaways

A retrospective on building Synthony: an app that turns audio — a file
upload, a YouTube link, a Spotify link, or a QR-scanned link — into
practice-ready piano sheet music at three difficulty tiers. Built solo,
2026-08-31 to 2026-09-16 (193 commits, 7 active build days), from empty
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

Moved to [`TAKEAWAYS_LESSONS.md`](TAKEAWAYS_LESSONS.md) — the full
retrospective (17 lessons across transcription accuracy, tempo
detection, the difficulty engine, and process) was pushing this file
well past the project's own ~400-line guideline. Below, "By the numbers"
and "What's next" reference specific lessons by title; look them up
there.

## By the numbers

- **193 commits**, empty repo to two complete pipelines plus a hardening
  pass, a discovery-sweep bug-fix pass, a production-readiness pass, and
  the entire 2026-09-16 portfolio-review backlog, across 7 active build
  days spanning 2026-08-31 to 2026-09-16
- **285 automated backend tests** (plus a separate frontend Vitest suite),
  4,339 lines of backend test code vs. 2,556 lines of backend source
  (more test code than implementation — a deliberate TDD habit, not an
  accident)
- **A measured ground-truth transcription accuracy number, for the first
  time**: 0.956 aggregate F1 (precision 0.977, recall 0.935) against 5
  held-out MAESTRO test-split clips (7,707 ground-truth notes), replacing
  "seems about as good as before" with an actual number
- **A measured difficulty-tier perception check, for the first time**: of
  5 self-rated pieces (15 tier outputs), Easy tied Medium in 3, and Hard
  rated *lower* than Medium in 3 — the rule-based Easy<Medium<Hard
  complexity ordering doesn't reliably match perceived sight-reading
  difficulty
- **A heuristic plausibility scorer** (`score_plausibility()`, 5 checks,
  8 TDD tests) that caught a real, previously-invisible register-overlap
  issue in `arrange_instrumental_big_rock`'s output on its first real run
- **41 frontend tests** (was 33), closing the one real gap in frontend
  coverage (`ScoreViewer.tsx`) after finding the other two named
  components already had tests
- **Time signature detection** (3/4 vs. 4/4, madmom's joint beat+downbeat
  tracker), closing out the entire 2026-09-16 portfolio-review backlog
  (312 backend tests total, was 278 at the start of that backlog)
- **Big Rock's half-time tempo misread: root cause confirmed AND fixed**
  (318 backend tests, was 312) — an onset-midpoint correction heuristic
  doubles beat density when a strong majority of detected inter-beat
  intervals have a comparably strong onset at their midpoint. Verified
  against real cached audio: corrected `bpm_at()` reads ~203-213 BPM
  (was ~109-111, the misread) and, more importantly, the actual
  notated-duration histogram shifts from ~75-77% "16th note" (the
  original complaint) to mostly quarter/eighth notes — see RESUME.md
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
instead — see `TAKEAWAYS_LESSONS.md`. The "production readiness" pass that
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
  0.935 / 0.956 over 7,707 ground-truth notes. See "A measured accuracy
  number beats 'seems about as good as before'" in `TAKEAWAYS_LESSONS.md`.
  Unblocks the next backlog item (validating difficulty tiers against
  real human judgment, which depends on this eval existing first).
- **Resolved**: that next item — validating the rule-based difficulty
  tiers (`app/difficulty/`) against real human sight-reading judgment —
  is done. Reused `quality_harness/run_baseline.py`'s existing flow
  (no new harness) to generate real Easy/Medium/Hard MusicXML for the
  same 5 MAESTRO clips; the user rated all 15 outputs 1-10 for
  sight-reading difficulty. Result: Easy tied Medium in 3/5 pieces, Hard
  scored lower than Medium in 3/5 — the rule-based ordering doesn't
  reliably track perceived difficulty. See "Construction-order isn't the
  same thing as perceived difficulty" in `TAKEAWAYS_LESSONS.md`
  for the full analysis and why (the rules touch rhythm/note-count, not
  melodic/harmonic complexity). n=5 is too thin to redesign the
  difficulty engine on alone, but it's a real, measured signal that a
  learned or complexity-aware difficulty model is worth investigating.
- **Resolved**: the backlog's third item — an automatic quality proxy for
  the listening pass — is done. `score_plausibility()` (5 heuristic
  checks: hand balance, register overlap, note-duration sanity,
  voice-count sanity, note-density sanity) flags gross RH/LH failures
  without a human listening first, wired into `run_baseline.py`. Only
  the hand-balance threshold is empirically calibrated (against Big
  Rock's old real defect); the rest are documented as reasonable
  guesses. Caught a real, previously-unnoticed register-overlap issue in
  `arrange_instrumental_big_rock`'s Medium/Hard tiers on its first real
  run — see "A heuristic proxy found a real issue on the first real run"
  in `TAKEAWAYS_LESSONS.md`.
- **Resolved**: the backlog's fourth item — a frontend test suite — is
  done, and turned out narrower than described. `DifficultyTabs.test.tsx`
  and `UploadForm.test.tsx` already existed (33 passing tests, CI already
  running them); the real gap was `ScoreViewer.tsx`, mocked out entirely
  by `DifficultyTabs.test.tsx` and never itself exercised. Added
  `ScoreViewer.test.tsx` (8 tests: OSMD load success/failure, zoom
  clamping, fullscreen toggle, blob download, PDF-export error path,
  print event wiring), mocking OSMD/jsPDF/svg2pdf at the module level.
  41 tests total now; lint and production build both clean. See "Check
  whether the backlog item is still true before designing the fix" in
  `TAKEAWAYS_LESSONS.md`.
- **Resolved**: the backlog's fifth and final item (explicitly optional,
  lowest priority) — extending time-signature detection past the fixed
  4/4 assumption — is done, closing out the entire 2026-09-16
  portfolio-review backlog. `detect_time_signature()` runs madmom's joint
  beat+downbeat tracker to distinguish 3/4 from 4/4, wired through
  exactly like `tempo_qpm`/`key_signature` already were. 14 new tests
  (312 total, was 298). See "A synthetic test can silently validate the
  wrong thing" in `TAKEAWAYS_LESSONS.md` for a real gotcha caught along the
  way — a synthesized test click track initially validated nothing at
  all, its apparent success actually the silent-audio fallback
  coincidentally matching the expected answer.
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
- **Confirmed and now fixed**: the second hypothesis — that the detected
  tempo itself is a half-time misread — was confirmed by ear (a
  doubled-BPM render matches the real recording's backbeat better than
  the detected-BPM render). A drums-stem-preferred routing change shipped
  first and is fully tested, but direct verification against Big Rock's
  actual drums stem showed it alone doesn't fix the misread — see "A
  plausible root-cause hypothesis still needs direct verification" in
  `TAKEAWAYS_LESSONS.md`. The onset-midpoint correction heuristic that actually
  fixes it (`_correct_half_time_misread()` in `app/tempo/detect.py`) was
  then built via TDD and verified against the same real cached audio:
  corrected `bpm_at()` moved from ~109-111 BPM to ~203-213 BPM, and a
  regenerated Hard-tier MusicXML's notated-duration histogram shifted
  from ~75-77% "16th note" (the original readability complaint) to
  mostly quarter/eighth notes. Uncommitted, pending the user's own
  listening confirmation. See `RESUME.md`.
- **Broadening past pop/rock** — instrumentals, rap, orchestral, and
  multi-melody songs are explicitly out of scope for the current
  arrangement engine, deferred on purpose until the pop/rock case was
  solid rather than half-solving a harder problem first.
- **A few explicitly-parked, not-forgotten items**: distinguishing
  multiple simultaneous instruments within Demucs's catch-all "other"
  stem is a real quality ceiling with no clean fix available yet, and any
  further LH onset-cleanup work is intentionally on hold unless listening
  actually surfaces it as a problem, rather than fixed pre-emptively.
