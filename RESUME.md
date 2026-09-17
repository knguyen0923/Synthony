# Resuming Synthony

## What's left to do (as of 2026-09-16, continued session)

Goal: a recorded demo video + resume-ready summary (not live deployment).
Two items block finishing that goal, both needing the user directly —
everything else on the demo-prep punch list is done (see below):

1. **Listen to the two Big Rock tempo-fix MIDI files** in
   `~/Downloads/synthony-arrangements/bigrock_hard_{before,after}-tempo-onset-fix.mid`
   and confirm the fix sounds right, so `backend/app/tempo/detect.py` +
   its test file (currently uncommitted, deliberately held back) can be
   committed. Not required for the demo video itself (neither picked demo
   song is Big Rock), but still an open thread from earlier this session.
2. **Look at the app in an actual browser** and record the demo. This
   session verified both pipelines only at the API level (curl) because
   the Chrome extension wasn't connected — no one has actually looked at
   how the UI renders since the README/UX review. Dev servers were
   running on `localhost:8000`/`:5173` at the end of this session (Node
   22 for the frontend — `nvm use 22` first, the shell default v16
   silently fails `npm run dev`); may need restarting if a while has
   passed.

Demo songs already picked and verified end-to-end: `transcribe_moonlight_sonata`
(solo piano) and `arrange_song_C` (any-song, vocal-melody path) — see
"Demo song selection" below for why.

## 2026-09-16 (continued): demo/resume-prep pass

User's actual goal clarified: not live deployment, just a recorded demo
video + a resume-ready summary. Worked sequentially through a prioritized
punch list without stopping for input at each step (per explicit
instruction), pausing only where something genuinely needed the user:

- **README polish**: added a "Highlights" section (measured F1, the
  tempo bug-hunt story, test counts) right after the intro, for a
  resume-linked reader who won't dig into `TAKEAWAYS.md` unprompted.
- **Resume bullets drafted** (in-chat, not committed to a file) — 4
  bullets sourced from `TAKEAWAYS.md`'s real numbers, no padding.
- **Frontend UX re-checked, no change needed**: assumed the `/arrange`
  polling UI showed raw status enum strings — checked `arrange.ts` and
  `UploadForm.tsx` first and it already maps each stage to a friendly
  label (`STAGE_LABELS`) and renders errors through a styled alert, not
  raw JSON. No polish work needed here; don't re-propose this.
- **Fresh smoke test, both pipelines, real audio, via curl** (Chrome
  extension wasn't connected this session, so browser-driven UI
  verification couldn't run — still outstanding, see below): killed two
  stale dev-server processes, restarted backend cleanly and frontend
  under Node 22 (`nvm use 22`; the shell default v16 still silently
  fails `npm run dev`, same gotcha as the 2026-09-16 daytime session).
  `/health` clean, `/transcribe` against `transcribe_moonlight_sonata`
  succeeded, `/arrange` against `arrange_song_A/B/C` all succeeded. No
  errors in either server's log beyond known-harmless
  scikit-learn/torch/tflite version warnings.
- **Demo song selection, backed by `score_plausibility()`, not just
  picked**: ran the existing heuristic plausibility scorer
  (`quality_harness/metrics.py`) against all three tiers of all three
  `arrange_song_*` outputs — a check that had only ever been run against
  `arrange_instrumental_big_rock` before. **New finding**:
  `arrange_song_A` flags `note_density_sanity` on LH (Medium: 4.1
  notes/quarter-length; Hard: 6.2, plus `voice_count_sanity` peaking at
  7 simultaneous LH notes) — previously unnoticed, not yet root-caused.
  `arrange_song_B` flags `register_overlap` on RH (Medium 42.6%, Hard
  50.9% of RH notes below middle C) — the same failure shape as Big
  Rock's known issue, on a *vocal-melody* song this time, not the
  instrumental-fallback path — also new, also not yet root-caused.
  **`arrange_song_C` is clean on all three tiers, no flags at all** —
  picked as the "any song" demo track for this reason.
  `transcribe_moonlight_sonata` (already known-clean) is the solo-piano
  demo track. Neither `arrange_song_A`'s nor `arrange_song_B`'s new
  flags block the demo (just don't feature those two), but they're real
  open questions worth investigating if instrumental/arrangement-quality
  work resumes — a second, independent data point beyond Big Rock that
  the vocal-melody path isn't immune to hand-balance/register issues
  either.
- **Narration outline drafted** (in-chat) for the demo video, referencing
  the two picked songs and the measured numbers above.
- **Still outstanding, needs the user**: (1) listen to the two pending
  Big Rock tempo-fix MIDI files
  (`~/Downloads/synthony-arrangements/bigrock_hard_{before,after}-tempo-onset-fix.mid`)
  and confirm before that fix gets committed; (2) an actual visual/UI
  polish check in a real browser — the Chrome extension wasn't connected
  this session so only API-level (curl) verification happened, not a
  look at how the app actually renders.



Updated 2026-09-16 (later still). Two fixes committed on top of the
2026-09-12 work below (all local `main`, not pushed to `origin/main` —
hold until explicitly asked), then an audits batch (code review, security
review, dependency audits) and a docs-cleanup pass, then the user
confirmed by ear that Big Rock's tempo is a half-time misread, then a
drums-stem-based fix was designed, implemented, and tested — then proven
by direct execution against real audio to NOT actually fix it (see "Big
Rock tempo investigation" below for the full story). Per explicit user
decision, **Big Rock is now shelved** (superseding the earlier "stopped
here for now" framing) in favor of working through the 2026-09-16
portfolio-review backlog instead. That backlog's first item — a MAESTRO
ground-truth transcription accuracy eval — was brainstormed (spec + plan
written and committed) and fully implemented this session; see "Queued:
2026-09-16 portfolio-review Improvement Backlog" below for the real
measured numbers and what's next.

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

## Resumed 2026-09-16 (night): Big Rock onset-midpoint tempo fix — built, tested, verified against real audio

The user asked to resume the shelved Big Rock work (below) right after
the low-priority venv rebuild. Implemented the previously-designed-but-
not-built fix via TDD: `_correct_half_time_misread()` in
`app/tempo/detect.py` checks each madmom-detected inter-beat interval for
a comparably-strong onset (via `librosa.onset.onset_strength`) near its
midpoint; if a strong majority of intervals show one, concludes a
half-time misread and doubles beat density, snapping each inserted beat
to the real local onset peak (not the naive time-midpoint). Wired into
`detect_beat_map()` via a new `_apply_half_time_correction()` wrapper
(any failure here silently falls back to the uncorrected beat_times,
matching the module's existing degrade-gracefully pattern). 6 new tests
(4 pure-logic on synthetic onset-envelope arrays, 2 on real
fluidsynth-synthesized half-time-misread audio) — full backend suite: 318
passed (was 312).

**Verified against Big Rock's real cached audio** (both `harmony.wav` and
the `drums.wav` stem, still in `/tmp/bigrock_probe/`), not just synthetic
tests, per this investigation's own established standard (the drums-stem
routing fix earlier this session looked right in unit tests but was
disproven this same way):
- Raw `bpm_at()` still reads ~109-111 BPM (the known misread, unchanged —
  expected, since correction runs *after* raw detection). Corrected
  `bpm_at()` reads **~203-213 BPM** across both stems and sampled
  throughout the whole track (not just one point) — matching the
  ~215-220 BPM the user confirmed by ear earlier this session.
- **Regenerated Big Rock's actual Hard-tier MusicXML** end-to-end (real
  transcription of the cached bass/other stems, not a shortcut) and
  compared real notated-duration histograms via
  `quality_harness/metrics.py`'s `analyze_musicxml()`: pre-fix, ~75-77%
  of RH/LH notes fell in the "dotted-16th/8th" duration bucket — exactly
  the user's original complaint ("every note is a 16th or 32nd note").
  Post-fix, that collapses to ~12-20%, redistributing mostly into
  quarter/eighth-note buckets. This is the first *objective, measured*
  confirmation that the fix changes the actual notated rhythm, not just
  the exported tempo label — because `BeatMap.to_quarter_length()` (fed
  by the now-doubled beat density) drives real rhythm quantization
  throughout the pipeline, not only the `MetronomeMark` export.
  `score_plausibility()`'s register-overlap flag on Right Hand is
  essentially unchanged (77.7%→76.2%), confirming that's a separate,
  unrelated issue (see below), not something this fix touches or masks.
- Before/after MIDI exported for listening confirmation:
  `~/Downloads/synthony-arrangements/bigrock_hard_{before,after}-tempo-onset-fix.mid`.
  **Not yet listened to by the user** — objective metrics are strong but
  this project's own norm is real-audio listening confirmation before
  calling a fix done, so this is the next step, not a closed item.
- Changes uncommitted, per this session's established pattern for Big
  Rock work (staged for user review/decision, same as the earlier
  drums-stem routing change).

## Also this session (2026-09-16, night): housekeeping, no user input needed

Done after the user asked to "do everything that doesn't involve me
first" (register-overlap root-cause and the broader instrumental/
broadening-past-pop-rock items were explicitly left alone since those
tie into paused threads only the user can re-open):

- **`TAKEAWAYS.md` split**: it had grown to 566 lines, well past this
  project's own ~400-line file-size guideline. Moved the "What I
  actually learned, by area" section (17 lessons) out into a new
  `TAKEAWAYS_LESSONS.md`, fixed all "see the lesson above"
  cross-references to point at the new file. `TAKEAWAYS.md` is now 274
  lines (overview/stack/architecture/by-the-numbers/what's-next only).
- **Swept superseded listening-export MIDI files** from
  `~/Downloads/synthony-arrangements/` per the established norm (delete
  once a round is resolved, don't wait to be asked) — 15 MAESTRO
  difficulty-rating files (backlog 2b, already committed in
  `my_ratings.json`) and 6 plausibility-check files (backlog 3a, already
  committed). Confirmed with the user first since the harness's own
  permission classifier flagged the deletion (outside the repo, in
  `~/Downloads/`) for confirmation. Kept the two still-pending Big Rock
  before/after tempo-fix MIDI files untouched (see section above).
- Both changes are just docs/local-file cleanup — no test suite impact.
  `TAKEAWAYS_LESSONS.md` is untracked (new file), `TAKEAWAYS.md`'s edit
  is uncommitted, same as everything else pending in this session.

## Shelved: Big Rock tempo investigation — root cause CONFIRMED, fix designed but not built

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
- **Onset-midpoint correction heuristic: now built** (see the section
  above this one) — for each detected inter-beat interval, checks (via a
  librosa onset-strength envelope) whether there's a comparably strong
  onset near the midpoint; if a strong majority of intervals show one,
  concludes a half-time misread and inserts beats at those midpoints
  (snapped to the real local onset peak, not the naive time-midpoint),
  doubling `beat_times` density. Targets the actual ambiguity directly
  and doesn't depend on which stem it runs on, as originally designed.

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

## Next up whenever Big Rock/instrumental work is revisited

Both items below are on hold behind the 2026-09-16 portfolio-review
backlog (see that section) by explicit user decision, not in priority
order for the immediate next session:

- **Instrumental-arrangement-quality revisit** — the broader shelved
  feature Big Rock is one data point for. User explicitly said "I don't
  know how I feel about it yet" after the stem-split fix; stopped
  investing further until raised again.
- **Broadening past pop/rock** — instrumentals, rap, orchestral, and
  multi-melody songs, entirely out of scope for the current arrangement
  engine. Its own brainstorm-and-spec cycle, planned last.
- Explicitly **not** being pursued unless something above surfaces a
  reason to: distinguishing multiple simultaneous instruments within
  Demucs's catch-all "other" stem (no known fix), further LH
  onset-cleanup (nothing currently prompting it).

## Queued: 2026-09-16 portfolio-review Improvement Backlog

User pasted a "Synthony Improvement Backlog" (from a 2026-09-16 portfolio
review) into this session. Big Rock was explicitly **shelved** (not
"finish first" anymore — user chose to move on to this backlog instead)
per a later decision in this same session. Now being worked through in
priority order via brainstorming → spec → plan → implementation, one
sub-project at a time. Priority order from that doc, highest first:

- **Priority 2a — ground-truth transcription accuracy eval: DONE.**
  Spec: `docs/superpowers/specs/2026-09-16-maestro-ground-truth-eval-design.md`.
  Plan: `docs/superpowers/plans/2026-09-16-maestro-ground-truth-eval.md`.
  Implemented as `backend/scripts/ground_truth_eval/` (`clips.py` names 5
  MAESTRO test-split clips; `fetch_maestro_clips.py` pulls just those via
  `remotezip` HTTP range requests, never the full ~108GB archive;
  `metrics.py` wraps `mir_eval.transcription` for onset+pitch
  precision/recall/F1, 7 TDD unit tests; `eval.py` runs
  `transcribe_piano_audio_to_notes()` directly — no HTTP, no difficulty
  tiers — against each clip and reports per-clip + aggregate numbers).
  **Real measured result**: aggregate precision=0.977, recall=0.935,
  f1=0.956 over 7,707 ground-truth notes across 5 composers — see
  `TAKEAWAYS.md`'s new "A measured accuracy number beats 'seems about as
  good as before'" lesson for the full story and comparison against the
  checkpoint's own reported 0.9677 training F1. Full backend suite: 285
  passed (was 278; +7 new tests). Report-only, no CI gate, per the spec.
  **Unblocks 2b below.**
- **Priority 2b — validate difficulty tiers against real human
  judgment: DONE.** Brainstormed as bounded (reuses an existing flow, no
  spec/plan doc). `backend/scripts/quality_harness/run_baseline.py`'s
  `SOURCES` now includes the same 5 MAESTRO clips as 2a (referenced
  directly from `ground_truth_eval/assets/`, not duplicated) as
  `pipeline="transcribe"` entries — ran for real, produced Easy/Medium/
  Hard MusicXML for all 5 under
  `quality_harness/output/maestro-difficulty-ratings/<name>/`.
  `difficulty_ratings_template.json` is the blank 15-entry (5 pieces × 3
  tiers) template; `analyze_difficulty_ratings.py` reads a filled-in copy
  and reports per-piece ordering/violations/ties/stats (5 TDD unit tests,
  report-only). Full backend suite: 290 passed (was 285; +5 new tests).
  **User rated all 15 outputs** (`backend/scripts/quality_harness/my_ratings.json`,
  committed) via the real app (uploaded each `.wav` through the frontend
  at `localhost:5173`, judged each tier's rendered notation, 1-10 scale).
  **Real result**: Easy tied Medium in 3/5 pieces; Hard scored *lower*
  than Medium in 3/5 (a real ordering violation, not just a tie) — the
  rule-based Easy<Medium<Hard complexity ordering does **not** reliably
  track perceived sight-reading difficulty. Per the user's own notes, the
  rules simplify rhythm grid and LH note count but never touch melodic
  complexity, accidental density, or leaps — the things that actually
  drive perceived difficulty. See `TAKEAWAYS.md`'s new "Construction-order
  isn't the same thing as perceived difficulty" lesson for the full
  analysis. n=5 self-rated is too thin to redesign `app/difficulty/` on
  alone, but it's a real, measured signal a learned/complexity-aware
  difficulty model is worth investigating — no code change made to
  `app/difficulty/*.py` itself, this was validation only, per the
  original brainstormed scope.
  **Aside, found and fixed along the way**: two dev-server processes had
  gone stale (backend running since 2026-09-11, frontend since
  2026-09-01, neither reflecting any code committed since) — killed and
  restarted both; also found the frontend's `npm run dev` fails outright
  under the shell's default Node v16 (Vite 5 needs 18+) and needs
  `nvm use 22` first. Worth remembering for next time either server needs
  restarting.
- **Priority 3a — automatic quality proxy for the "listening pass": DONE.**
  Brainstormed as bounded (extends `metrics.py`, no spec/plan doc). No
  labeled good/bad corpus exists, so went heuristic (not a trained
  classifier), per the backlog's own first-listed option.
  `score_plausibility()` in `backend/scripts/quality_harness/metrics.py`
  flags gross RH/LH failures from the same `analyze_part()`-shaped stats
  `analyze_musicxml()` already computes: hand balance (<10% of total
  notes on one hand — calibrated against Big Rock's real historical
  defect, RH1169/LH29), register overlap (>30% of a hand's notes in the
  other hand's register, via a new `register_split` field), note-duration
  sanity (>40% shorter than a 16th note), voice-count sanity (>6
  simultaneous notes in one hand), note-density sanity (near-silent or
  implausibly dense). Report-only, a list of flagged issues, no
  aggregate score, no gate — only the hand-balance threshold is
  empirically calibrated, the rest are documented as reasonable-guess
  heuristics. Wired into `run_baseline.py` right after
  `analyze_musicxml()`. 8 TDD unit tests. Full backend suite: 298 passed
  (was 290; +8 new tests).
  **Real result, ran against the existing corpus**:
  `transcribe_moonlight_sonata` (Spec 1, solo piano) flags nothing across
  all 3 tiers. `arrange_instrumental_big_rock`'s Medium and Hard tiers
  flag a real register-overlap issue nobody had previously surfaced:
  41.5%/79.1% of RH notes fall below middle C — exactly the kind of
  gross-failure signal this was built to catch without a human listening
  first. Not yet root-caused (a new observation, not a fix) — worth
  investigating if instrumental-arrangement work resumes.
  **Also found and fixed along the way**: pytest's bare-module-name
  collision between `ground_truth_eval/metrics.py` and
  `quality_harness/metrics.py` — confirmed by direct reproduction that a
  naive `from metrics import ...` in a second `quality_harness/` test
  file would silently import the wrong module depending on collection
  order. The new test loads `quality_harness/metrics.py` by explicit file
  path instead. Worth remembering if either directory gets more tests.
- **Priority 3b — frontend test suite: DONE.** Turned out stale: checked
  before designing anything and found `DifficultyTabs.test.tsx` (3 tests)
  and `UploadForm.test.tsx` (7 tests) already existed and passed — 2 of
  the 3 named components were already covered, CI already runs the whole
  suite. The real gap was `ScoreViewer.tsx`, which
  `DifficultyTabs.test.tsx` mocks out entirely (`vi.mock("./ScoreViewer",
  ...)`) and so had never actually been exercised. Added
  `ScoreViewer.test.tsx` (8 tests): OSMD load success/failure, zoom
  clamping at 50%-250%, fullscreen toggle via a real `fullscreenchange`
  event, blob-based MusicXML download, the PDF-export no-pages-found
  error path, and `beforeprint`/`afterprint` page-format switching —
  mocking `opensheetmusicdisplay`/`jspdf`/`svg2pdf.js` at the module
  level (same technique the codebase already used to mock `ScoreViewer`
  itself). Deliberately not testing the actual multi-page SVG-to-PDF
  pixel output (would test the libraries, not this component). Full
  frontend suite: 41 passed (was 33; +8 new tests). Lint and production
  build (`tsc` + `vite build`) both clean.
- **Priority 4 (explicitly optional/lowest): DONE.** Brainstormed as
  bounded (mirrors the existing `tempo_qpm`/`key_signature` threading
  pattern exactly). `app/tempo/time_signature.py`'s
  `detect_time_signature()` runs madmom's joint beat+downbeat tracker
  (`beats_per_bar=[3, 4]`), splits into complete bars, and returns 3/4
  only when ≥4 bars were found and ≥90% agree on length — otherwise
  falls back to 4/4 (the previous, implicit behavior). Wired through
  `build_grand_staff_score()` (new `time_signature` param), a new
  `get_time_signature()` reader for Spec 1's Easy/Medium forwarding, and
  Spec 2's `arrange_pipeline.py` per-tier build loop, detected from the
  same audio source (drums stem or harmony mix) already used for tempo.
  14 new tests (7 pure logic, 3 on real fluidsynth-synthesized 3/4 and
  4/4 click tracks, 3 more for the `build_grand_staff_score`/
  `get_time_signature` wiring). Full backend suite: 312 passed (was 298).
  Verified end-to-end against the real running backend too.
  **Real gotcha caught along the way**: a first attempt at a synthetic
  test click track (identical-velocity onsets, same style as the
  existing beat-tracking tests) measured under `has_audible_signal`'s RMS
  floor — its apparent "correct" 4/4 result was actually the
  silent-audio fallback coincidentally matching, not real detection.
  Fixed by peak-normalizing the synthesized test audio before writing it.
  README's documented 4/4-only limitation updated.
  **This closes out the entire 2026-09-16 portfolio-review backlog**
  (2a, 2b, 3a, 3b, 4 — all done).

## Optional, lower priority

Empty — the one item previously carried here is resolved:

- **Broken local backend venv**: fixed this session by rebuilding via
  `bash backend/setup.sh` (user asked for this first, before resuming
  Big Rock work). Confirmed fixed: `which python`/`which pytest` now
  resolve inside `.venv` correctly (no more silent fallback to base
  Anaconda), and the full backend suite passes clean against it (312
  passed, matching the pre-rebuild count). Local machine state only, no
  commit.

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
- `docs/superpowers/specs/2026-09-16-maestro-ground-truth-eval-design.md`
  + `docs/superpowers/plans/2026-09-16-maestro-ground-truth-eval.md` —
  the MAESTRO ground-truth eval (backlog item 2a, done). The eval itself
  lives at `backend/scripts/ground_truth_eval/`.
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
