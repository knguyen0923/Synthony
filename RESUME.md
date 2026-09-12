# Resuming Synthony

Updated 2026-09-12 (later session). The `assign_hands` non-piano follow-up
flagged at the end of the last session is now resolved — via a mid-course
pivot, not the fix originally planned. Instrumental arrangement work is
**shelved** after this; focus is moving to piano transcription quality and
a production-readiness/bug-fix/polish pass. This is where things stand.

## assign_hands multi-instrument follow-up — resolved, merged locally, not yet pushed

Merged to local `main` (fast-forward, 7 commits, tests green: 252/252).
**Not pushed to `origin/main` yet** — hold on that until explicitly asked.

What happened, in order:

1. **Task 1–2:** Fixed `assign_hands`'s real bug — it forced every "lone
   note" onset unconditionally to RH, correct for solo piano but wrong for
   multi-instrument input. Fix: once *both* hands already have an
   established pitch centroid, let a lone note flow through the existing
   DP cost-scoring instead of the hard bypass; keep the original bypass
   for cold start. This fix is real and independently verified (Moonlight
   Sonata sounded correct after) — it stands on its own for Spec 1's
   solo-piano path (`hand_split.py`), regardless of what happened next.
2. **Task 4 (real-audio verification):** objectively fixed the RH/LH count
   imbalance (rock instrumental hard tier: 1169/29 → 670/540). But by-ear
   listening found it "sounds incoherent/scattered" despite the balanced
   counts.
3. **Investigation:** confirmed the flicker is structural, not a tuning
   gap — swept `SWITCH_PENALTY` against the real note stream and found
   balance and flicker are in direct opposition (a value strong enough to
   suppress flicker just recreates the original bug).
4. **Pivot (Task 5):** `_instrumental_variants` now transcribes the
   `bass` and `other` Demucs stems **separately** (bass→LH, other→RH)
   instead of mixing them and re-splitting by pitch continuity —
   eliminates the flicker structurally, since each hand is one
   continuously-transcribed real source. Confirmed better by ear against
   the actual shipped code (not just a prototype).

**Known, accepted trade-off, not resolved:** the "other" stem's pitch
range can dip below the bass stem's clamped LH range on the Hard tier, so
RH can occasionally sit lower than LH — a hand-crossing the old DP
approach specifically avoided. User heard both and preferred stem-split
anyway. Listed in the plan's Deferred section if this needs picking up
again.

Spec: `docs/superpowers/specs/2026-09-12-hand-split-instrumental-fix-design.md`
(includes the full pivot evidence). Plan: `docs/superpowers/plans/2026-09-12-hand-split-instrumental-fix.md`.
Executed via `superpowers:subagent-driven-development`; final whole-branch
review found 2 Important + 5 Minor stale-documentation issues (all from
the pivot leaving old comments/log lines/docstrings behind), fixed in one
pass, re-reviewed clean. SDD workspace already deleted.

## Instrumental arrangement — shelved, explicit user decision

After hearing the fixed output, the user's own words: "i dont know how i
feel overall with the arrange instrumental yet." Explicit decision: finish
and merge the `assign_hands`/hand-split fix (done, above), then **stop
investing further in arrange-instrumental quality** for now — it's an open
question to revisit later, not a blocker on anything else. Don't
resume work on this feature without the user raising it again.

Additional data point for that future revisit: user also felt **Big
Rock's tempo sounds too slow** in the arrangement output. Not investigated
— explicitly logged rather than acted on, since it's the same shelved
feature.

## Next up (as of this session's end): production readiness + bug fix/polish

- User flagged **"the tempo is so slow"** on **Big Rock** (the shelved
  instrumental track above, not a piano transcription as first assumed).
  Explicit decision: log it here, don't investigate now — it's another
  data point for whenever arrange-instrumental gets revisited, not a
  separate active thread.
- User asked for a plan to get this project **"ready for production"**
  (their words: "even though this is a personal project") plus a
  **bug-fix-and-polish pass** on the codebase. Not yet scoped — needs a
  proper brainstorm (what "production ready" means here: deployment
  target, who else might use it, security/auth expectations, uptime
  expectations, etc.) before turning into a plan. This is the actual next
  work thread.

## Everything else from before — status

All previously-listed items (CI, docker-compose env-shadowing, native
arm64 Docker builds, frontend Vitest suite) are done and pushed — see git
history / `TAKEAWAYS.md` for detail.

**Still not done:** wiring `npm test` into `.github/workflows/ci.yml` (CI
currently only runs frontend build/lint) — small, deliberately left for an
explicit decision since it's a shared CI-pipeline file. This is a natural
candidate for the production-readiness pass above.

## Optional, lower priority (unchanged from before)

- `/transcribe` still runs its full ML pipeline synchronously on the
  event loop — worth revisiting only if `/transcribe` needs genuine
  concurrent-request handling someday.
- A handful of Minor findings from past reviews were deliberately left as
  cosmetic/low-risk, not bugs — durable record is each work's design spec,
  not repeated here.
- Two long-standing, deliberately-parked items: distinguishing multiple
  simultaneous instruments within Demucs's catch-all "other" stem, and
  further LH onset-cleanup work (on hold unless listening surfaces it as
  a problem).

## Where to look for more context

- `TAKEAWAYS.md` — the full retrospective from the production-hardening
  pass.
- `docs/superpowers/specs/2026-09-12-hand-split-instrumental-fix-design.md`
  and `docs/superpowers/plans/2026-09-12-hand-split-instrumental-fix.md` —
  this session's fix, spec and plan, both updated with the pivot's
  real-audio evidence.
- `docs/superpowers/specs/2026-09-12-instrumental-arrangement-design.md`
  and `docs/superpowers/plans/2026-09-12-instrumental-arrangement.md` —
  Track 3 Phase 1's original spec and plan (the work that surfaced the
  `assign_hands` bug this session fixed).
