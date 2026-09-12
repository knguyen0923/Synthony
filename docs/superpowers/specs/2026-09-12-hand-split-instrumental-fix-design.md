# Hand-Split Fix for Multi-Instrument Input (assign_hands Follow-up)

## Motivation

Track 3 Phase 1 (instrumental arrangement routing, see
`docs/superpowers/specs/2026-09-12-instrumental-arrangement-design.md`)
shipped correct detection/routing for instrumental songs, but its
mandatory real-audio verification surfaced a quality bug in a function it
*reuses*, not one it introduces: `assign_hands`
(`backend/app/notation/hand_assignment.py`), Spec 1's continuity-aware DP
hand-split, originally built and tuned against solo piano input only.

On the one real full-band rock instrumental tested, the DP split was
badly unbalanced: RH received 1169 notes (83% of them bass-register,
below MIDI 48), LH received only 29 notes, all the same pitch. Routing
was correct (this song correctly took the instrumental branch); the
*arrangement quality* of the hand split it produced was not. This is not
a crash or an exception — it's a structurally valid but musically wrong
two-hand split, the kind of bug only real-audio listening verification
surfaces, not unit tests against synthetic fixtures.

This spec was deliberately deferred out of Track 3 Phase 1's own plan
(see that spec's "Open risk" section) because it's Spec 1's DP tuning
surface, shared by two call sites, and needed its own investigation
rather than a same-pass patch.

## Root cause

`assign_hands` (`hand_assignment.py:211-266`) groups notes into onset
clusters (`_group_by_onset`), then for onset groups of size ≥ 2, runs an
exact DP search over legal RH/LH mask assignments scored by continuity
(EMA pitch centroids), physical span, hand-crossing, and switch-hysteresis
costs (`_legal_masks`/`_score_mask`). But for onset groups of size 1, this
entire scoring path is bypassed:

```python
if n == 1:
    masks = [(True,)]  # hand_assignment.py:226-227
```

This forces every lone note straight to RH, unconditionally. It's
documented (module docstring, `hand_assignment.py:32-38`) as a deliberate
special case preserving the pre-DP convention that a melody note is
"always RH" even when playing solo. For **solo piano**, this is a
reasonable prior: a real pianist's lone note at a given instant is
almost always the melodic voice, and onset groups of size 1 are
relatively rare (most onsets bundle a melody note with accompaniment).

For a **multi-instrument mix** (Demucs's "other" stem — guitar, synth,
strings, etc. — transcribed as one polyphonic signal by Basic Pitch),
this prior breaks down: bass notes and chord tones frequently land on
their own distinct onsets rather than bundling with other notes, so a
much larger fraction of onset groups are size 1, and nearly all of them
default to RH regardless of register or the note's own continuity
history. The final whole-branch review of Track 3 Phase 1 identified
this as the likely root cause; this spec investigates and fixes it.

## Diagnostic: onset-grouping tolerance

Before changing the RH-bypass rule, rule in or out a contributing
factor: whether `ONSET_ROUND_DECIMALS` (currently 3 decimal places — 1ms
tolerance) is too tight for multi-instrument transcription's onset
timing jitter, causing notes that *should* group into one onset (e.g. a
bass note and a chord tone struck together but transcribed a few ms
apart) to fall into separate, spuriously-lone-note onset groups.

**Method:** instrument `_group_by_onset` (or a standalone script wrapping
it) against the real full-band rock instrumental track used for Track 3
Phase 1 verification (or an equivalent fresh instrumental track if that
one is no longer cached). Measure the fraction of onset groups of size 1,
and for a sample of them, whether another note starts within a small
window after (e.g. 20-50ms) that a wider tolerance would have merged in.

**Result (measured):** On the real full-band rock instrumental track
(arrange_instrumental_big_rock.mp3), 967 onset groups were observed, 925
of them size-1 (95.7%). Of those lone-note onsets, only 85 (9.2%) fell
within 30ms of the next onset — below the 15% MATERIAL_THRESHOLD. **Ruled
out:** mis-grouping from `ONSET_ROUND_DECIMALS` is not a material
contributor. The observed lone-note rate is mostly genuine (bass and chord
tones landing on distinct onsets), not a grouping artifact. `ONSET_ROUND_DECIMALS`
is left unchanged; proceed to Task 2 (the DP-scoring fix) without a
merge-window implementation.

## Fix: DP-scored lone-note assignment with a soft RH bias

Remove the hard bypass. Onset groups of size 1 flow through the same
`_legal_masks`/`_score_mask` path as every other size, with one addition:
a new tunable constant, `LONE_NOTE_RH_BIAS`, added as a flat cost
(alongside the existing `SWITCH_PENALTY`/`CROSSING_PENALTY` flat terms in
`_score_mask`) to whichever candidate mask assigns the lone note to LH
instead of RH.

This is a **bias**, not a floor or absolute-pitch threshold — it
competes with the DP's real continuity/span/crossing costs rather than
overriding them, consistent with the module's existing design principle
of using no absolute-pitch threshold (so a melody can still legitimately
dip into bass register without forced hand reassignment):

- **Solo piano:** lone notes are sparse and typically continue an
  already-established RH-ward melodic line; continuity cost plus the new
  bias both favor RH, so behavior should be unchanged in practice.
- **Multi-instrument mix:** lone low-register notes with an established
  LH-ward continuity history find that the continuity cost of jumping to
  RH's centroid outweighs the small bias, so they correctly route to LH.

`_legal_masks`' existing fallback (all masks legal if none satisfy
`HARD_SPAN_SEMITONES`) already covers the n=1 case once it's no longer
bypassed — no new error-handling path needed.

No call-site changes: both `hand_split.py:255` (Spec 1) and
`arrange_pipeline.py:120` (Spec 2's instrumental branch) keep calling
`assign_hands(notes)` with an unchanged signature — the fix is internal
to the function.

## Fallback (documented, not the default plan)

If real-audio verification (below) shows the piano path regresses in a
way `LONE_NOTE_RH_BIAS` tuning can't resolve, fall back to a call-site-
gated dual mode instead: add `assign_hands(notes, allow_lone_note_dp:
bool = False)`, defaulting to the exact current bypass behavior (zero
regression risk to Spec 1), with only Spec 2's instrumental branch
passing `allow_lone_note_dp=True`. This is a weaker fix (doesn't unify
the algorithm, only patches the affected caller) and should be treated
as a fallback, not a first choice.

## Testing

**Unit tests** (`backend/tests/test_hand_assignment.py`), TDD as usual:

- New synthetic test(s) covering the multi-instrument shape: a sequence
  of alternating low-register lone-note onsets with an established
  LH-ward centroid, asserting they route to LH — this is the case that
  fails today and should pass after the fix.
- Existing lone-note tests must still pass unchanged as the piano
  regression guard: `test_lone_low_note_is_melody_and_goes_to_right_hand`,
  `test_sustained_low_melody_run_stays_in_right_hand`,
  `test_highest_simultaneous_note_is_melody_rest_are_accompaniment`, and
  the flicker/hysteresis tests. If `LONE_NOTE_RH_BIAS` needs tuning to
  keep these green, that tuning happens in this loop, not deferred.
- Indirect coverage (`test_hand_split.py`, `test_arrange_pipeline.py`)
  re-run as-is; no expected behavior change there beyond what the new
  unit tests already cover directly.
- If the onset-grouping diagnostic finds mis-grouping material: a
  separate targeted synthetic test for the merge-window behavior, kept
  distinct from the bias tests so a future regression points at the
  right mechanism.

**Real-audio verification** (mandatory per this project's standing
practice — unit tests alone have repeatedly missed real bugs on this
pipeline; Hard-tier listening only, per this project's standing scope
preference):

- Re-run the same real full-band rock instrumental track from Track 3
  Phase 1 verification through `/arrange`'s instrumental branch; confirm
  the RH/LH imbalance (1169 RH / 29 LH, 83% RH bass-register) is
  resolved to a plausible two-hand split.
- Re-run at least one real solo-piano track through Spec 1's
  `/transcribe` path to confirm no audible regression.
- A second real instrumental track, if easily available, is a nice-to-
  have (stronger evidence the fix generalizes) — not blocking.

## Tuning parameters to expect adjusting by ear

- `LONE_NOTE_RH_BIAS` — new constant; starting value TBD during
  implementation (start small relative to `SWITCH_PENALTY`'s 4.0 and
  `CROSSING_PENALTY`'s 3.0, since it's meant to be a tie-breaking nudge,
  not a dominant cost), tuned against both the piano regression tests and
  the real instrumental track's listening result.
- `ONSET_ROUND_DECIMALS` — only touched if the diagnostic step finds
  mis-grouping material; otherwise left at its current value.

## Post-implementation update: the DP fix wasn't enough (2026-09-12)

Tasks 1-4 above shipped as designed and real-audio verification confirmed
the count-imbalance was fixed (rock instrumental hard tier: RH/LH went from
1169/29 to 670/540). But the user's own listening pass on that same output
found it "sounds incoherent/scattered" despite the balanced counts. This is
a real, additional finding beyond what this spec anticipated -- the fix
correctly matched its own design goal, but the design goal (get the DP to
route lone notes to LH when continuity favors it) turned out not to be
sufficient for real musical quality on this kind of input.

**Root cause of the flicker, confirmed by direct experiment:** reconstructed
the actual note stream `assign_hands` receives for "Big Rock" (Kevin
MacLeod's public-domain track behind `arrange_instrumental_big_rock.mp3`)
from the exported hard-tier MusicXML, and measured a 43.7% adjacent-note
hand-switch rate (time-ordered across both hands) -- far above what the
existing `SWITCH_PENALTY` hysteresis was tuned to keep rare. Sweeping
`SWITCH_PENALTY` against this same real note stream showed the switch rate
and the RH/LH balance are in direct opposition, not independently tunable:

| `SWITCH_PENALTY` | RH / LH | switch rate |
|---|---|---|
| 4.0 (shipped) | 675 / 535 | 44.3% |
| 8.0 | 1093 / 117 | 7.2% |
| 20.0+ | 1206 / 4 | 0.1% (== the original bug) |

A flat hysteresis penalty strong enough to suppress flicker just makes the
DP stick with whichever hand it started in for the whole piece -- i.e. it
recreates the original bug. This is a structural property of
per-onset-continuity hand splitting applied to a *mixed, multi-instrument*
note stream, not a tuning gap: solo piano continuity assumes one
performer's two hands tracking a genuinely continuous musical line each;
"Big Rock"'s harmony_path is bass and "other" (guitar/synth/whatever
Demucs's catch-all stem contains) mixed into one signal and transcribed as
if it were one instrument, so consecutive "notes" in the merged stream
often really belong to two different instruments alternating in time, not
one line drifting in pitch. No single per-note hysteresis constant can be
both loose enough to let genuine register separation happen and tight
enough to prevent switching on every alternation.

**The fix: stop mixing, stop reassigning.** Confirmed via direct
transcription of the already-separated Demucs stems (`bass.wav`: 381
notes, range 28-56; `other.wav`: 284 notes, range 28-69) that transcribing
each stem *independently* -- bass stem -> LH, "other" stem -> RH, no
`assign_hands` call at all -- produces a 57%/43% balanced split where each
hand's part is one continuously-transcribed real source, structurally
immune to flicker (there is no per-note hand decision being made at all).
Built a prototype (bypassing `assign_hands` entirely, reusing
`notes_to_part`/`shift_into_range`/`cap_simultaneous_notes` exactly as
`_instrumental_variants` already does) and exported it for listening
alongside the DP-based version; the user's verdict: the stem-split version
sounds better. **This is the direction to implement** (see Task 5 in the
plan) -- `_instrumental_variants` should transcribe `stems.bass` and
`stems.other` separately instead of mixing them into `harmony_path` and
calling `assign_hands`.

**Known remaining risk, not fully resolved:** the "other" stem's range (28-
69) overlaps the bass stem's range (28-56) at the bottom -- "other"
occasionally dips as low as bass's floor, so RH could momentarily hold a
lower note than LH at the same instant (a hand-crossing the old DP-based
approach was specifically designed to penalize/avoid). The user's listening
verdict preferred this trade-off over the flicker, but this is a real,
named, un-eliminated risk of the new approach, not a claim that it's
strictly better in every respect.

**What this means for `assign_hands` itself (Task 2, already shipped):**
that fix stands on its own merit independent of this pivot -- it's a real,
verified improvement to solo piano's own hand-assignment (Spec 1's
`notes_to_grand_staff` call site), confirmed by real-audio listening on the
Moonlight Sonata sounding correct after the change. It is simply no longer
what solves the instrumental branch's problem, since the instrumental
branch will stop calling `assign_hands` at all per Task 5.

## Open risk (carried forward, not resolved by this spec)

The commit that introduced `assign_hands` (`25d513b`) already flagged
that it only reasons about exact-onset groups, not duration overlap
across nearby-but-distinct onsets — some real transcriptions may still
pile up sustained-duration notes in one hand this way. This is a
separate, pre-existing gap from the one this spec fixes and is not
addressed here.
