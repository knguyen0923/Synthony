# Resuming Synthony

Updated 2026-09-12 (evening session). Track 3 Phase 1 (instrumental
arrangement) is now **implemented, real-audio verified, reviewed, and
pushed to `origin/main`**. This is what's left.

## Peer session note (unresolved, carried forward)

A peer Claude Code session called `synthony-bd` has been active on this
same repo/working-directory throughout this session (`ListAgents` still
shows it `busy`, started ~3h ago). A status-check message sent to it this
session was held pending the user's approval and never got a reply.
No collision happened this time — `git fetch origin` at the end of this
session shows no commits from anywhere but this session, and the working
tree stayed clean throughout. Still, **before starting new work, check
`ListAgents` for whether `synthony-bd` (or any other peer session) is still
active and whether it has pushed anything new** — the same caution that
applied last session still applies.

## Track 3, Phase 1: instrumental arrangement — done, merged, one known follow-up

Broadening `/arrange` past pop/rock, scoped to **instrumentals only**
(orchestral/rap/multi-melody deferred to later, separate specs). Shipped
as 5 commits on `main`:

- `2afc03c` — `_is_instrumental` predicate (Task 1)
- `c550bc1` — `_instrumental_variants`, the DP hand-split (Task 2)
- `b5a787f` — wired the branch into `run_arrange_pipeline` (Task 3)
- `7616733` — **fix, found during mandatory real-audio verification:** the
  original `MIN_MELODY_NOTES` raw-count threshold couldn't work for any
  value (a real vocal song at 64 notes and a real instrumental track at 71
  notes need opposite classifications — raw count is confounded with clip
  duration). Replaced with a note-density check
  (`MIN_MELODY_NOTE_DENSITY = 0.8` notes/sec).
- `6e38e6d` — **fix, found by the final whole-branch review:** instrumental
  RH's Easy/Medium tiers were silently keeping the lowest pitch of every
  chord (invisible to Hard-tier-only listening); added the same
  fail-loudly empty-harmony guard `_lh_variants` already has; richer
  routing log line (note count + density, for future tuning data).

Full design spec (now includes both post-implementation updates above):
`docs/superpowers/specs/2026-09-12-instrumental-arrangement-design.md`.
Plan (all 3 tasks executed via `superpowers:subagent-driven-development`,
per-task + final whole-branch review, both clean): `docs/superpowers/plans/2026-09-12-instrumental-arrangement.md`.

**Known follow-up, not fixed in this pass (deliberately deferred, both by
the plan's own text and independently affirmed by the final review):**
`assign_hands`'s continuity-aware DP split (reused from Spec 1, tuned only
against solo piano) produces a badly unbalanced hand split on real
non-piano input. The one real instrumental song tested (a full-band rock
instrumental) put 1169 notes in RH (83% of them bass-register, below MIDI
48) and only 29 notes — all the same pitch — in LH. Routing/detection (this
plan's actual deliverable) is correct and verified; arrangement *quality*
on non-piano input is not. Root-cause lead from the review: `assign_hands`
always assigns a lone note at an onset to RH, which is correct for solo
piano but likely wrong when nearly every onset in a multi-instrument mix
has size 1. **This needs its own investigation and its own real-audio
verification pass** — see the spec's "Open risk" section for full detail.
Not scheduled yet; flagging here so it doesn't get lost.

## Everything else from before — status

All previously-listed items (CI, docker-compose env-shadowing, native
arm64 Docker builds, frontend Vitest suite) are done and pushed — see
git history / `TAKEAWAYS.md` for detail, not repeated here since nothing
changed on them this session.

**Still not done:** wiring `npm test` into `.github/workflows/ci.yml` (CI
currently only runs frontend build/lint) — small, deliberately left for an
explicit decision since it's a shared CI-pipeline file.

## Optional, lower priority (unchanged from before)

- `/transcribe` still runs its full ML pipeline synchronously on the
  event loop — worth revisiting only if `/transcribe` needs genuine
  concurrent-request handling someday.
- A handful of Minor findings from the hardening pass's final review, and
  from this session's instrumental-arrangement reviews, were deliberately
  left as-is (all confirmed low-risk/cosmetic, not bugs) — the plan's SDD
  ledger has already been deleted (per `superpowers:subagent-driven-development`'s
  own cleanup step, since its final review came back clean); the design
  spec's post-implementation notes are the durable record now.
- Two long-standing, deliberately-parked items: distinguishing multiple
  simultaneous instruments within Demucs's catch-all "other" stem, and
  further LH onset-cleanup work (on hold unless listening surfaces it as
  a problem).
- The `assign_hands` non-piano DP-split quality follow-up (see above) —
  this is new this session, higher-priority than the other parked items
  since it's a known real-audio-confirmed gap, not a theoretical one.

## Where to look for more context

- `TAKEAWAYS.md` — the full retrospective from the production-hardening
  pass.
- `docs/superpowers/specs/2026-09-12-instrumental-arrangement-design.md`
  and `docs/superpowers/plans/2026-09-12-instrumental-arrangement.md` —
  Track 3 Phase 1's spec and plan, both updated with real-audio-verification
  and final-review findings.
- `docs/superpowers/specs/2026-09-01-any-song-arrangement-design.md` —
  has the original "Phase 6 (later, separate spec) — Broaden beyond
  pop/rock" note that Track 3 picks up.
