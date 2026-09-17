# Resuming Synthony

Updated 2026-09-16 (later). Two fixes committed on top of the 2026-09-12
work below (all local `main`, not pushed to `origin/main` — hold until
explicitly asked), then an uncommitted batch of audits (code review,
security review, dependency audits) and a docs-cleanup pass, then the
user confirmed by ear that Big Rock's tempo is a half-time misread, then
a drums-stem-based fix was designed, implemented, and tested — then
proven by direct execution against real audio to NOT actually fix it
(see "In progress" below for the full story). Per explicit user
decision, stopped here rather than immediately building the fix that
would actually work.

## Done this session (2026-09-16), committed

Both chosen because they're verifiable by inspection (score/XML
structure, a mocked-timing regression test) — no audio listening
required, unlike everything else queued in this file.

- **Ingestion event-loop fix**: `_ingest_and_validate_duration` (shared
  by `/transcribe` and `/arrange`) now runs `ingest()` (yt-dlp/Spotify)
  and `librosa.get_duration()` via `run_in_threadpool`, closing the gap
  the `/transcribe` pipeline fix's own final review had flagged and
  deliberately scoped out. Regression test uses the same
  TestClient-as-context-manager + mocked-blocking-call technique as
  that fix's own test (`backend/tests/test_api.py`) — confirmed it
  fails without the fix (5s block) and passes with it.
- **Tempo-marking export fix**: exported MusicXML now carries an
  explicit tempo (a music21 `MetronomeMark`) instead of leaving
  playback speed entirely up to the importing software's own default —
  this is the confirmed half of the Big Rock complaint below. Wired
  through the one shared `build_grand_staff_score()` helper via a new
  `tempo_qpm` param, using `BeatMap.bpm_at()` (which already existed in
  `app/tempo/detect.py`, docstring literally anticipating this: "intended
  for eventually annotating tempo-change markings in exported
  notation"). A matching `get_tempo()` reader carries it forward through
  Easy/Medium the same way `get_title()` already does. Full backend
  suite: 273 passed (was 269; +4 new tests for these two fixes).
- `TAKEAWAYS.md` updated (`What's next` section, stack table, test/line
  counts). This file (`RESUME.md`) updated to match.
- **Stray doc edit reverted**: `docs/superpowers/specs/2026-09-12-production-readiness-pass-design.md`
  had picked up an accidental paste (`cool sounds good t ome` prepended
  to its title line) before this session started. Flagged to the user,
  reverted.

## Also this session (2026-09-16), not committed: audits + docs cleanup

All of this is inspection/verification and doc changes only — no
production code changed in this half of the session. Not committed yet;
left for the user to review and commit (or not).

- **Discovery-sweep code review** (`/code-review high`, whole-codebase
  intent — a previous instance of this same sweep had been killed
  mid-run in an earlier session, before a `/clear`): came back clean.
  Traced its two most-suspected candidate concerns out to REFUTED: (a) a
  possible duplicate `MetronomeMark` when Easy/Medium tiers forward
  tempo — not an issue, because `to_easy`/`to_medium` call
  `get_hand_parts` then `quantize_part`/`shift_into_range`, which only
  copy `part.flatten().notes` + clef into a fresh `Part`, never other
  stream elements, so `get_tempo()` reading the original +
  `build_grand_staff_score` re-inserting once is the only tempo mark
  written (`backend/app/difficulty/quantize.py:20-32`,
  `backend/app/difficulty/range_shift.py:13-21`); (b) whether moving
  `ingest()` off the event loop via `run_in_threadpool` was unsafe — it
  isn't, it's pure synchronous I/O into a per-request unique `dest_dir`,
  no shared mutable state. Tempo and ingestion-offload tests re-run live,
  all pass.
- **Security review** (`security-review` skill) of the same 5-commit
  diff (tempo-marking + ingestion-offload fixes): no HIGH/MEDIUM
  findings. Both changes are pure internal numeric computation (tempo
  forwarding) or a threadpool-execution-context change with unchanged
  call signatures — no new injection/auth/crypto/data-exposure surface.
- **Dependency audits**: `npm audit --production` in `frontend/` — 0
  vulnerabilities. Backend `pip-audit` first hit a local-machine-only
  snag (see the new "Optional, lower priority" item below for the
  broken-venv details) but, worked around, came back essentially clean:
  one hit, `setuptools 80.10.2` → `PYSEC-2026-3447` (fixed in 83.0.0) —
  checked what it actually is: a macOS-specific Unicode-normalization
  bug in `setuptools`' sdist-building `MANIFEST.in` exclusion matching,
  relevant only to *building* a package for distribution (which
  Synthony doesn't do), not runtime. `requirements.txt` already pins
  `setuptools<81` deliberately (madmom/resampy need the legacy
  `pkg_resources` API setuptools 81+ dropped) — informational only, no
  action taken; upgrading would break the pipeline for no benefit.
  **Net result of all four checks above: clean code review, clean
  security review, clean dependency audit (frontend and backend) —
  nothing left to fix by inspection.**
- **Docs cleanup**: re-audited all 7 specs and 13 plans in
  `docs/superpowers/` against the current codebase (not just trusting
  the 2026-09-12 session's judgment). Deleted one: `docs/superpowers/plans/2026-09-02-phase4-async-job-infra.md`
  — its entire Task 3 architecture (`generate_lh_variants`,
  `detect_chords`, `app.arrangement.engine`) was the chord-symbol-driven
  pipeline retired by the 2026-09-02 LH-true-transcription rewrite; no
  dangling references to it existed anywhere else in the repo. Kept
  everything else, including some that looked stale at first glance but
  turned out to still document real, currently-accurate outcomes under
  renamed internals (e.g. `2026-09-02-spec2-key-signature.md` and
  `2026-09-02-spec2-real-tempo.md` both reference a `detect_chords`
  function that's since been renamed to `detect_key_and_tempo`, but the
  actual deliverables they describe — key signature and real tempo
  threaded through Spec 2 — are exactly what's still live in
  `arrange_pipeline.py` today) or that already self-document their own
  pivots in place (e.g. `2026-09-12-hand-split-instrumental-fix-design.md`
  has its own "Post-implementation update" section covering the later
  per-stem-transcription pivot away from its original DP-split fix).
- This `RESUME.md` update itself.

## Also this session (2026-09-16), not committed: drums-stem tempo fix (implemented, tested, then disproven)

New production code + tests this time (unlike the audits batch above).
Full story is in the "In progress: Big Rock tempo investigation" section
below; summary: `app/tempo/detect.py` gained `has_audible_signal()`,
`app/arrange_pipeline.py`'s `run_arrange_pipeline` now prefers Demucs's
`drums` stem over the bass+other harmony mix for beat detection when it
has real signal (5 new tests, TDD, full suite 278 passed). Verified
against Big Rock's real cached drums stem before declaring it fixed —
and it isn't: still reads ~107-109 BPM on the real isolated drums track,
same as before. Kept anyway (harmless, tested) per user decision; the
onset-midpoint correction heuristic that would actually fix it is
designed but not built. Also noticed and fixed in passing: the local
`backend/.venv` had drifted to `setuptools 84.0.0`, above the
deliberate `<81` pin in `requirements.txt` (needed for `resampy`'s
`pkg_resources` import) — broke test collection entirely until
`pip install "setuptools<81"` restored it. Local venv state only, not a
commit.

## Done and merged in the 2026-09-12 session

- **Production-readiness pass** (`docs/superpowers/specs/2026-09-12-production-readiness-pass-design.md`,
  `docs/superpowers/plans/2026-09-12-production-readiness-pass.md`): Demucs
  stem-directory cleanup (going-forward + a one-time sweep of ~2.6GB of
  pre-existing dead stems), `/health` reporting ffmpeg/piano-model status
  plus a startup warning, rotating file logging with a safe fallback, and
  `backend/setup.sh`. Final whole-branch review found 4 Important + 9
  Minor findings; 7 fixed in one wave, rest parked with rulings (see the
  plan's own ledger notes in its commit history).
- **`/transcribe` event-loop fix + small backlog batch**
  (`docs/superpowers/plans/2026-09-12-backlog-and-transcribe-fix.md`):
  `/transcribe`'s CPU-bound pipeline now runs via `run_in_threadpool`
  instead of blocking the event loop — `MAX_CONCURRENT_JOBS` is reachable
  for the first time. Caught its own plan defect mid-flight: the first
  version of the regression test reused this test file's shared,
  non-context-managed `TestClient`, which never shares one event-loop
  portal across requests and would have passed even against the broken
  code — verified empirically (both by the implementer and the final
  reviewer, in a throwaway worktree) before trusting the fix. Also fixed:
  a missing failure-path test, log-dir test isolation, a logger-restore
  fixture, `setup.sh --clear`, and a `HealthResponse` Pydantic model.
- **Docs cleanup**: deleted 5 plan files whose entire deliverable code no
  longer exists (the chord-symbol-driven `app/arrangement/` package and
  its chord-recognition/dynamics/key-awareness plans — all retired by the
  2026-09-02 LH-true-transcription rewrite). No specs deleted — every doc
  in `docs/superpowers/specs/` still has at least some currently-accurate
  content per its own internal notes.
- `CLAUDE.md` added: session operating rules (max 3 concurrent agents,
  avoid ~100k+ token single tasks, pause-and-update-this-file at 90%
  session usage, ~400-line file-size guideline, keep README/TAKEAWAYS
  current).
- `README.md`/`TAKEAWAYS.md` both refreshed to current state (commit/test
  counts, a README Status section, TAKEAWAYS lessons from both passes
  above) — modeled after an example project (PikaRAG) the user shared as
  a format/quality-bar reference.

## In progress: Big Rock tempo investigation — root cause CONFIRMED, fix not yet designed

User asked to work through the shelved-instrumental backlog in order:
Big Rock's tempo complaint → the broader instrumental-quality revisit →
broadening past pop/rock. This is the first of those three.

**2026-09-16, by-ear confirmation**: user listened to both tempo
variants (converted to MIDI via `music21` since MusicXML isn't
GarageBand-importable — `/tmp/bigrock_probe/hard_tempo_detected_111bpm.mid`
vs. `hard_tempo_doubled_222bpm.mid`) and confirmed **the doubled
222 BPM version's note-density/backbeat matches the real Big Rock
recording better than the 111 BPM detected version.** This confirms the
half-time-misread hypothesis below: both madmom and librosa locked onto
half Big Rock's true tempo (~215-220 BPM actual vs. ~107-110 BPM
detected), a known shared failure mode for driving rock backbeats where
both algorithms' onset-strength-autocorrelation approach can't
distinguish the true beat from its half-time subdivision.

**Root cause confirmed for Big Rock specifically. A fix was designed,
implemented, tested — and then proven NOT to actually fix it, by direct
execution against real audio:**

- Brainstormed (bounded path) a fix: run beat detection on Demucs's
  `drums` stem (already extracted, never previously used anywhere in
  the codebase) instead of the bass+other harmony mix, on the
  hypothesis that the harmony mix was an ambiguous signal for beat
  tracking and drums would be clearer. Implemented via TDD: new
  `has_audible_signal()` in `app/tempo/detect.py` (cheap RMS gate, 3
  unit tests) plus routing logic in `run_arrange_pipeline`
  (`app/arrange_pipeline.py`) preferring `stems.drums` over
  `harmony_path` when it has real signal (2 more tests). Full suite:
  278 passed (was 273).
- **Then ran it against Big Rock's real cached drums stem
  (`/tmp/bigrock_probe/stems/htdemucs/arrange_instrumental_big_rock/drums.wav`)
  as a sanity check before declaring victory — and it does NOT fix the
  misread.** `detect_beat_map()` on the real isolated drums stem still
  reads ~107-109 BPM, identical to the harmony-mix result. The
  half-time ambiguity isn't caused by cross-instrument interference in
  the mix (which drums-only would remove); it's that Big Rock's actual
  backbeat pattern's strongest hits genuinely sit at the half-time
  rate, so madmom locks onto that same pulse whether or not other
  instruments are present. See TAKEAWAYS.md's new "A plausible
  root-cause hypothesis still needs direct verification" lesson.
- **Current state, per explicit user decision**: keep the drums-stem
  routing change (harmless, fully tested, arguably still a reasonable
  default for other songs even though it didn't help this one) but
  stop here for now rather than immediately implement the next fix.
  Changes are uncommitted, staged for the user to review (matching
  this session's established norm).
- **Still-needed fix, designed but not implemented**: the
  onset-midpoint correction heuristic from the original (pre-pivot)
  brainstorm — for each detected inter-beat interval, check (via a
  librosa onset-strength envelope) whether there's a comparably strong
  onset near the midpoint; if a strong majority of intervals show one,
  conclude a half-time misread and insert beats at those midpoints
  (snapped to the real local onset peak, not the naive time-midpoint),
  doubling `beat_times` density. This targets the actual ambiguity
  directly and doesn't depend on which stem it runs on. Not yet built.

**Both original hypotheses are now resolved** (superseding the
"Open, unconfirmed hypothesis"/"Next step, waiting on the user" text
this section used to have): (1) the missing-tempo-marking bug — fixed
and committed, confirmed via direct execution that no export ever
carried a `MetronomeMark`; (2) the half-time-misread hypothesis —
confirmed by ear on 2026-09-16 (see above): a doubled-BPM (222)
render's note-density/backbeat matches the real recording better than
the detected-BPM (111) render. The drums-stem fix attempt and its
disproof are detailed above. `/tmp/bigrock_probe/` still holds all
probe artifacts (real Demucs stems, harmony mix, both tempo-variant
MusicXML/MIDI exports) — outside the repo, scratch/throwaway, not
committed, safe to regenerate or delete.

## Next up after Big Rock resolves

- **Instrumental-arrangement-quality revisit** — the broader shelved
  feature Big Rock is one data point for. User explicitly said "I don't
  know how I feel about it yet" after the stem-split fix; stopped
  investing further until raised again. Now being raised again, in the
  order above.
- **Broadening past pop/rock** — instrumentals, rap, orchestral, and
  multi-melody songs, entirely out of scope for the current arrangement
  engine. Its own brainstorm-and-spec cycle, planned last.
- Explicitly **not** being pursued unless something above surfaces a
  reason to: distinguishing multiple simultaneous instruments within
  Demucs's catch-all "other" stem (no known fix), further LH
  onset-cleanup (nothing currently prompting it).

## Queued: 2026-09-16 portfolio-review Improvement Backlog (not started, not yet saved as a doc)

User pasted a "Synthony Improvement Backlog" (from a 2026-09-16 portfolio
review) into this session. Explicitly deprioritized behind Big Rock —
user said "finish Big Rock first" when asked which to tackle. **Exists
only in this session's chat history right now, not saved to any file**
(offered to save it as a spec/backlog doc; not yet answered). Priority
order from that doc, highest first:

- **Priority 2a — ground-truth transcription accuracy eval**: the
  existing quality harness (`backend/scripts/quality_harness/`) only
  diffs metrics run-over-run, never checks correctness against a known
  answer. Plan: pull a handful of MAESTRO dataset clips (piano + ground
  truth MIDI — the same corpus `piano_transcription_inference` was
  trained on), run them through the Spec 1 solo-piano pipeline, compute
  real note-level precision/recall/F1 (onset + pitch) against ground
  truth.
- **Priority 2b — validate difficulty tiers against real human
  judgment**: the difficulty engine (`app/difficulty/easy.py` /
  `medium.py` / `hard.py`) is pure rule-based, no check against how
  people actually rate playability. Depends on 2a existing first;
  collect real (even self-rated) sight-readability judgments and check
  whether the rule-based tiers track perceived difficulty.
- **Priority 3a — automatic quality proxy for the "listening pass"**:
  the quality harness's own docstring admits a human still has to
  listen to judge real quality. Consider a lightweight automatic proxy
  (pitch/rhythm plausibility scorer, or a classifier for obviously bad
  arrangements) to cut down how often a human has to listen, not
  replace it.
- **Priority 3b — frontend test suite**: frontend correctness is
  currently verified manually in a browser only (per the README). Even
  a thin Vitest + React Testing Library layer on `DifficultyTabs`,
  `UploadForm`, `ScoreViewer` would close this gap.
- **Priority 4 (explicitly optional/lowest)** — extend key/tempo
  detection past the current fixed-4/4-time-signature assumption
  (documented limitation, not a bug).

## Optional, lower priority

One real item, newly found this session — everything previously carried
here is resolved (see below):

- **Broken local backend venv**: `backend/.venv`'s `activate` script and
  nearly every installed console-script (`pip`, `pytest`, `uvicorn`,
  `fastapi`, `demucs`, `yt-dlp`, etc.) have shebangs/paths hardcoded to
  `.venv-py311`, a directory that no longer exists on this machine — the
  venv was apparently created at that name originally, then renamed to
  `.venv` without regenerating its scripts. Effect: `source
  .venv/bin/activate` silently fails to put the real venv on `PATH` and
  falls back to base Anaconda instead. Confirmed local-only, gitignored
  machine state (`.gitignore` line 4 covers `.venv`; no CI workflow
  references `setup.sh` or this venv) — nothing to fix via a commit.
  Fix is a multi-minute `bash backend/setup.sh` rebuild (re-clones/builds
  `madmom`, reinstalls `demucs`/`torch`/etc.); declined to run it
  unprompted given the time/bandwidth cost, offered to the user, not yet
  answered.

Checked 2026-09-16 (earlier in the day): this queue was empty before the
above. Both previously-carried items are resolved:

- The ingestion event-loop item — fixed this session (see above).
- The "handful of Minor findings parked" from the production-readiness
  pass's final review (4 Important + 9 Minor found; 7 fixed immediately)
  — traced through `docs/superpowers/plans/2026-09-12-backlog-and-transcribe-fix.md`,
  which explicitly cleared "the 5 actionable small items parked" (LOG_DIR
  test isolation, a logger-restore fixture, `setup.sh --clear`, the
  `HealthResponse` model, and the missing dest_dir-cleanup-on-failure
  test — all committed in `807c41a`/`e1d7cd3`). That accounts for all 6
  remaining after the first wave (9 Minor + 4 Important − 7 fixed = 6; 6
  − 5 = 1), leaving exactly one: the "install recipe lives in 4 places"
  (README/`setup.sh`/CI/Dockerfile) observation, which that plan's own
  "Deferred" section already ruled **informational only, no concrete fix
  proposed** — and checking now, that's correct, not stale: Dockerfile
  and `ci.yml` each already cross-reference README's install steps in
  their own comments, and each has a real reason to duplicate rather than
  share a script (Dockerfile needs `maturin` for the arm64 `sphn` build
  that CI doesn't; sourcing `setup.sh` from inside a Docker build would
  mean creating/activating a venv inside a container, which is its own
  design decision, not a quick win). Nothing left to pick off here
  without a real design call.

## Where to look for more context

- `TAKEAWAYS.md` — full project retrospective, kept current.
- `docs/superpowers/specs/2026-09-12-production-readiness-pass-design.md`
  + `docs/superpowers/plans/2026-09-12-production-readiness-pass.md` —
  the production-readiness pass.
- `docs/superpowers/plans/2026-09-12-backlog-and-transcribe-fix.md` — the
  `/transcribe` fix + small backlog batch (no separate spec; brief
  in-chat design instead, per its own header).
- `docs/superpowers/specs/2026-09-12-hand-split-instrumental-fix-design.md`
  — the stem-split pivot Big Rock's investigation builds on.
- This file's "Queued: 2026-09-16 portfolio-review Improvement Backlog"
  section above — the only place that backlog is recorded right now.
