# Resuming Synthony

Updated 2026-09-12 (afternoon session). Everything from the previous
RESUME.md's "do these first" and "bigger, needs its own scoping pass"
sections is now **done and pushed to `origin/main`**. This is what's left.

## Important: another session may be active on this same repo

Partway through this session, a peer Claude Code session called
`synthony-bd` was found also working on this exact repo (same working
directory, not a separate clone) — it independently landed on the same
Track 3 idea and committed a competing version of the design spec
(`271b840`, which is what's actually on `origin/main` now — a different,
earlier draft from *this* session got overwritten and is gone except in
git history at `72db05c`). A ping was sent to `synthony-bd` asking for a
status update; it was still marked `busy` and no reply had landed by the
time this session ended. **Before starting any Track 3 implementation
work, check `ListAgents` for whether `synthony-bd` (or any other peer
session) is still active and whether it has pushed anything new to
`arrange_pipeline.py` or the plan/spec docs** — avoid duplicating or
colliding with work in progress elsewhere.

## Track 3, Phase 1: instrumental arrangement — spec + plan ready, not yet implemented

Broadening `/arrange` past pop/rock was scoped down to **instrumentals
only** for this phase (orchestral/rap/multi-melody deferred to later,
separate specs — see the design doc's Motivation section for why).

- **Design spec** (committed, pushed): `docs/superpowers/specs/2026-09-12-instrumental-arrangement-design.md`
- **Implementation plan** (committed locally as `28d5dc8`, **not yet
  pushed**): `docs/superpowers/plans/2026-09-12-instrumental-arrangement.md`
  — a 3-task TDD plan, verified line-by-line against the current
  codebase (not just the spec's pseudocode). No new modules; reuses
  `assign_hands`, `cap_simultaneous_notes`, `notes_to_part`, and
  `transcribe_audio_to_notes`, all of which already exist.
  - Task 1: `_is_instrumental` predicate
  - Task 2: `_instrumental_variants` (DP hand-split)
  - Task 3: wire the branch into `run_arrange_pipeline` + **mandatory
    real-audio verification** (submit the existing 3-song corpus to
    confirm they're unaffected, submit a genuine instrumental track,
    listen to the Hard-tier output — this is the load-bearing check,
    since `assign_hands`'s tuning was only ever validated against solo
    piano audio, not a multi-instrument harmony mix)

**Next step:** decide whether to execute this plan (via
`superpowers:subagent-driven-development`, as the plan itself specifies)
— check on `synthony-bd` first per the note above, then push `28d5dc8`
and proceed.

## Everything else from before — status

1. ~~Push `main`, watch first CI run~~ — done, CI passed (both jobs
   green, cold caches primed).
2. ~~Fix docker-compose env-shadowing bug~~ — done (`eae7c4e`), verified
   with `docker compose config`.
3. ~~Decide on native arm64 Docker builds~~ — done and fully verified
   (`7ed12f3`): added a Rust/cmake/libopus-dev/maturin toolchain so
   `sphn` builds from source on arm64. Confirmed twice — `sphn` and
   the full `requirements.txt` install succeed, and a complete
   `docker compose build backend` now finishes end-to-end (image
   exports and unpacks cleanly). The only failure along the way was an
   unrelated host disk-space exhaustion (Docker/OrbStack ran the host
   down to single-digit GB free at one point) — not a defect in the fix.

**New, from this session:** a frontend automated test suite was added
(Vitest + React Testing Library) — 27 tests across pure functions
(`classifyLink`, `extractErrorMessage`), component logic (`UploadForm`,
`DifficultyTabs`, `InputScreen`), and the `/arrange` job-polling flow.
Committed (`b155c9a`), pushed, lint/build clean. `ScoreViewer`'s OSMD
rendering and `QrScanButton`'s camera access remain manually-verified
only (not unit-testable, per the design proposal's own reasoning).
**Not yet done:** wiring `npm test` into `.github/workflows/ci.yml` (CI
currently only runs frontend build/lint) — small, deliberately left for
an explicit decision since it's a shared CI-pipeline file.

## Optional, lower priority (unchanged from before)

- `/transcribe` still runs its full ML pipeline synchronously on the
  event loop — worth revisiting only if `/transcribe` needs genuine
  concurrent-request handling someday.
- A handful of Minor findings from the hardening pass's final review
  were deliberately left as-is (all confirmed low-risk, not bugs).
- Two long-standing, deliberately-parked items: distinguishing multiple
  simultaneous instruments within Demucs's catch-all "other" stem, and
  further LH onset-cleanup work (on hold unless listening surfaces it as
  a problem).

## Where to look for more context

- `TAKEAWAYS.md` — the full retrospective from the production-hardening
  pass.
- `docs/superpowers/specs/2026-09-12-instrumental-arrangement-design.md`
  and `docs/superpowers/plans/2026-09-12-instrumental-arrangement.md` —
  Track 3 Phase 1's spec and plan (see above).
- `docs/superpowers/specs/2026-09-01-any-song-arrangement-design.md` —
  has the original "Phase 6 (later, separate spec) — Broaden beyond
  pop/rock" note that Track 3 picks up.
