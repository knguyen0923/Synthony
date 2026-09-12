# Resuming Synthony

Updated 2026-09-12 (later session). Two full passes have landed on local
`main` since the last update (not pushed to `origin/main` — hold until
explicitly asked): a production-readiness pass, then a follow-up batch
fixing `/transcribe`'s event-loop blocking. Currently mid-investigation
on the shelved instrumental-arrangement backlog (Big Rock's tempo
complaint) — see "In progress" below for exactly where that's paused.

## Done and merged since the last update

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

## In progress: Big Rock tempo investigation (spike, not yet a plan)

User asked to work through the shelved-instrumental backlog in order:
Big Rock's tempo complaint → the broader instrumental-quality revisit →
broadening past pop/rock. This is the first of those three, currently
paused mid-investigation, not yet a plan.

**Confirmed by direct execution** (ran the real production code path
against the real audio — real Demucs stems, real bass+other mix, real
tempo detection, real instrumental-variant construction — not just read
the code): **no arrangement Synthony has ever exported carries a tempo
marking.** Checked directly on Big Rock's real Hard-tier score:
`score.flatten().getElementsByClass('MetronomeMark')` returns zero
matches. This is a genuine, universal gap — playback speed is entirely
up to whatever default the importing software assumes, decoupled from
whatever tempo was actually detected. For Big Rock specifically, the
math says a standard 120 BPM MIDI default would render it ~11% *faster*
than the source (206s vs. 231s), not slower — so this bug is real but
doesn't cleanly explain the "too slow" complaint's direction by itself.

**Open, unconfirmed hypothesis:** two independent tempo-detection
algorithms (madmom, librosa) agree tightly at ~107-110 BPM for Big Rock,
on both the full mix and the real bass+other stem mix the pipeline
actually uses. Tight agreement is not proof of correctness here — both
algorithms share the same onset-strength-autocorrelation approach, and a
"half-time" reading of a driving rock backbeat (true tempo ~215-220 BPM)
is one of the most common shared failure modes in tempo detection. This
would make every note render at double the note-value it should, which
reads/feels sluggish independent of the metronome-mark bug's math. Can't
confirm or rule out without listening — no audio playback available in
this session's environment.

**Next step, waiting on the user:** offered to render both tempo
versions (detected vs. doubled) of Big Rock's arrangement for a by-ear
comparison, or to just fix the confirmed no-tempo-marking bug first and
revisit the octave-error question only if that turns out not to be the
whole story. User has not yet answered which they want.

Probe artifacts (real Demucs stems, harmony mix, exported test
MusicXML) are in `/tmp/bigrock_probe/` — outside the repo, scratch/
throwaway, not committed, safe to regenerate or delete.

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

## Optional, lower priority (carried forward, unchanged)

- `/transcribe`'s *ingestion* step (YouTube/Spotify download, duration
  check) still blocks the event loop the same way the pipeline itself
  used to — caught by the fix above's own final review, deliberately
  scoped out as its own follow-up (same `run_in_threadpool` shape) rather
  than expanding an already-approved merge.
- A handful of Minor findings parked across both passes above (see each
  plan's commit history for exact rulings) — none load-bearing, all
  independently actionable later.

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
