# Instrumental Arrangement Design (Track 3, Spec A)

## Motivation

Spec 2's `/arrange` pipeline hard-wires two fixed roles onto Demucs's four
stems: `vocals` always becomes RH (forced monophonic), `bass`+`other`
always becomes LH (real polyphonic transcription, capped in voice count).
This is correct for pop/rock songs with a sung lead line, but for a
genuinely instrumental song — no vocals at all — the `vocals` stem is
near-silent, `extract_melody_notes` finds little or nothing, and the
result is a silently degraded output: not a crash, just an empty or
near-empty right hand for the whole piece, with no error signal to the
user. This was flagged as the highest-priority case in Track 3's broader
"beyond pop/rock" research specifically because of that silent-failure
risk — worse than an explicit rejection. Orchestral, rap, and true
multi-melody support are explicitly out of scope for this spec (see the
Track 3 research writeup); orchestral in particular stacks a second,
unvalidated risk (Demucs's stem categories don't match orchestral
instrumentation at all) that this spec doesn't take on.

The chosen fix reuses machinery that already exists and is already
proven, rather than inventing new melody-detection logic: Spec 1's
continuity-aware DP hand-split (`app.notation.hand_assignment.
assign_hands`) was built to solve exactly this problem — "many
simultaneous voices, no predetermined melody/harmony split" — for solo
piano transcription. An instrumental song's harmony content (bass+other,
same audio Spec 2 already separates and mixes for today's LH) is the same
kind of input: no single predetermined "the melody," just notes that need
splitting into two physically playable hands.

## Current State (for reference)

- `arrange_pipeline.py::run_arrange_pipeline` always calls
  `extract_melody_notes(stems.vocals)` for RH and `extract_lh_notes
  (harmony_path)` (where `harmony_path = mix_wav_files(stems.bass,
  stems.other, ...)`) for LH, unconditionally — no branching on input
  content.
- `app.melody.extract.extract_melody_notes`: Basic Pitch on the vocals
  stem, then `reduce_to_monophonic` collapses overlaps to one line, always
  producing a monophonic RH source.
- `app.lh.extract.extract_lh_notes(audio_path, max_voices=HARD_MAX_VOICES)`:
  Basic Pitch on the harmony mix with `minimum_note_length=
  LH_MINIMUM_NOTE_LENGTH_MS` (180ms, tuned for busy non-piano audio), then
  `cap_simultaneous_notes` bounds simultaneous voices to a plausible
  per-hand maximum (4).
- `app.notation.hand_assignment.assign_hands(notes) -> (rh_notes,
  lh_notes)`: Spec 1's DP split — used today only by
  `app.notation.hand_split.notes_to_grand_staff`, which is Spec 1's
  sole entry point (`app.main::transcribe`). Spec 2 never calls it.
- `app.notation.hand_split.notes_to_part(notes, part_id, seconds_per_quarter,
  beat_map) -> stream.Part`: builds a single Part from a flat note list,
  in onset order, no hand-splitting — the generic building block both
  `build_melody_part` and `build_lh_part` wrap with pipeline-specific
  extras (RH's legato cleanup, LH's register shift).
- `app.notation.hand_split.build_grand_staff_score(rh, lh, title,
  key_signature)`: shared score assembler, already supports an optional
  `key_signature` — used by Spec 2's per-tier loop today, **not** forwarded
  by `notes_to_grand_staff` (Spec 1 doesn't detect a key at all, so this
  never came up before).
- `app.difficulty.quantize.quantize_part(part, grid, max_voices=1)` and
  `app.difficulty.range_shift.shift_into_range(part, low, high)`: the
  generic tier-derivation pair both hands already use in
  `arrange_pipeline._rh_variants`/`_lh_variants`.

## New Architecture

```
mix.wav
  └─ separate_stems() → vocals.wav, drums.wav, bass.wav, other.wav
        ├─ extract_melody_notes(vocals.wav) → melody_notes   [unchanged call]
        │
        │   len(melody_notes) < MIN_MELODY_NOTES ?
        │        │                           │
        │       no (has vocals)             yes (instrumental)
        │        │                           │
        │   existing Spec 2 path        NEW instrumental path:
        │   (vocals→RH, bass+          harmony_path = mix_wav_files(bass, other)  [already computed]
        │    other→LH, as today)       notes = transcribe_audio_to_notes(harmony_path, minimum_note_length=180ms)
        │                              rh_notes, lh_notes = assign_hands(notes)        [Spec 1's DP split]
        │                              rh_notes = cap_simultaneous_notes(rh_notes, 4)
        │                              lh_notes = cap_simultaneous_notes(lh_notes, 4)
        │                              rh_base = notes_to_part(rh_notes, "RH", ...)
        │                              lh_base = shift_into_range(notes_to_part(lh_notes, "LH", ...), *HARD_LH_RANGE)
        │                              (then existing _rh_variants/_lh_variants-shaped
        │                               tier derivation: quantize_part + shift_into_range,
        │                               same grids/ranges/voice caps as today)
        └────────────────────────────────────────────────────┘
                           ▼
       build_grand_staff_score(rh_variant, lh_variant, key_signature=...) per tier — UNCHANGED
                           ▼
                MusicXML export × 3 — UNCHANGED
```

Detection reuses the RH extraction Spec 2 already runs unconditionally
today — no separate energy/silence detector. `extract_melody_notes`
(Basic Pitch + `reduce_to_monophonic`) runs exactly as it does now; if the
resulting note list is implausibly short for a full song
(`len(melody_notes) < MIN_MELODY_NOTES`), that's treated as "no real
vocal melody" and the pipeline takes the instrumental branch instead of
building RH from those (near-empty or noise-artifact) notes. This
correctly also catches noisy/bleed-only vocals stems, not just true
silence, since the signal is "did a plausible melody come out," not "is
there any energy at all."

Key/tempo detection (`detect_key_and_tempo`, `detect_beat_map`) keeps
running over the same `harmony_path` as today, unconditionally — the
instrumental branch doesn't change this at all, since that mix was never
vocals-derived in the first place.

## Components

### `arrange_pipeline.py` (modified)

> **Post-implementation update (2026-09-12, after real-audio verification):**
> the code block below is the original design. Real-audio verification
> found `MIN_MELODY_NOTES` (a raw note count) could not work for *any*
> threshold value — it's confounded with clip duration, not just
> mis-tuned: a real vocal song measured at 64 notes needed to classify as
> non-instrumental, while a real instrumental track measured at 71 notes
> (over a much longer clip) needed to classify as instrumental, and
> 71 > 64 makes any single count cutoff impossible. The shipped predicate
> uses note **density** (notes/second over the detected notes' own span)
> instead — see `_is_instrumental`/`_melody_note_density` in
> `backend/app/arrange_pipeline.py` for the actual implementation. The
> shipped `_instrumental_variants` also passes explicit `max_voices` to
> `quantize_part` for RH's Easy/Medium tiers (`1` and `MAX_VOICING_TONES`
> respectively) — the version below omits this, which silently kept the
> lowest pitch of every RH chord instead of the highest-velocity one; caught
> in the final whole-branch review, not real-audio verification, since
> Hard-tier-only listening bypasses `quantize_part` entirely. It also
> raises `ValueError("No harmonic content detected")` on empty
> transcription, matching `_lh_variants`'s existing contract. See the
> **Open risk** section below for the one finding real-audio verification
> did surface: `assign_hands`'s DP-split output on real non-piano input.

```python
MIN_MELODY_NOTES = 8  # tuning constant — a real sung melody in a full-length
                       # song produces far more than this; expect to adjust
                       # by ear/real-audio testing, same as this project's
                       # other extraction thresholds.
                       #
                       # SUPERSEDED — see the post-implementation note above.
                       # Shipped as MIN_MELODY_NOTE_DENSITY (notes/second),
                       # not a raw count.

def _is_instrumental(melody_notes: list[NoteEvent]) -> bool:
    return len(melody_notes) < MIN_MELODY_NOTES

def _instrumental_variants(harmony_path: str, seconds_per_quarter: float, beat_map: BeatMap):
    """RH/LH variants for a song with no real vocal melody: transcribe the
    harmony mix directly (no vocals involved) and split it into hands via
    Spec 1's continuity-aware DP (assign_hands), instead of Spec 2's usual
    vocals-are-RH/bass+other-are-LH fixed roles. Mirrors _rh_variants/
    _lh_variants' shape exactly so downstream tier derivation is identical."""
    notes = transcribe_audio_to_notes(harmony_path, minimum_note_length=LH_MINIMUM_NOTE_LENGTH_MS)
    rh_notes, lh_notes = assign_hands(notes)
    rh_notes = cap_simultaneous_notes(rh_notes, MAX_SIMULTANEOUS_VOICES_PER_HAND)
    lh_notes = cap_simultaneous_notes(lh_notes, MAX_SIMULTANEOUS_VOICES_PER_HAND)

    rh_base = notes_to_part(rh_notes, part_id="RH", seconds_per_quarter=seconds_per_quarter, beat_map=beat_map)
    lh_base = shift_into_range(
        notes_to_part(lh_notes, part_id="LH", seconds_per_quarter=seconds_per_quarter, beat_map=beat_map),
        *HARD_LH_RANGE,
    )
    rh_variants = {
        "easy": shift_into_range(quantize_part(rh_base, EASY_GRID), *EASY_RH_RANGE),
        "medium": shift_into_range(quantize_part(rh_base, MEDIUM_GRID), *MEDIUM_RH_RANGE),
        "hard": rh_base,
    }
    lh_variants = {
        "easy": shift_into_range(quantize_part(lh_base, EASY_GRID, max_voices=1), *EASY_LH_RANGE),
        "medium": shift_into_range(quantize_part(lh_base, MEDIUM_GRID, max_voices=MAX_VOICING_TONES), *MEDIUM_LH_RANGE),
        "hard": lh_base,
    }
    return rh_variants, lh_variants
```
*(This block is the original design, kept for historical context — it does
not match the shipped code. See the update note above and the actual
source for what shipped.)*

`run_arrange_pipeline` calls `extract_melody_notes(stems.vocals)` exactly
as today, then branches:

```python
melody_notes = extract_melody_notes(str(stems.vocals))
if _is_instrumental(melody_notes):
    rh_variants, lh_variants = _instrumental_variants(str(harmony_path), seconds_per_quarter, beat_map)
else:
    lh_variants = _lh_variants(str(harmony_path), seconds_per_quarter, beat_map)
    rh_variants = _rh_variants(melody_notes, seconds_per_quarter, beat_map)
```

`harmony_path`/`detected_key`/`seconds_per_quarter`/`beat_map` are all
computed once, before the branch, exactly as today — nothing about key
or tempo detection changes.

`HARD_MAX_VOICES` (from `app.lh.extract`) and
`MAX_SIMULTANEOUS_VOICES_PER_HAND` (from `app.notation.hand_split`) are
both already 4 — the instrumental branch reuses
`MAX_SIMULTANEOUS_VOICES_PER_HAND` (Spec 1's constant, since it's
capping DP-split hands, the same operation Spec 1 already does) rather
than introducing a third identically-valued constant.

**Why `notes_to_part` + manual tier derivation, not
`notes_to_grand_staff` + `generate_variants` wholesale:** Spec 1's
`generate_variants` (`to_easy`/`to_medium`/`to_hard`) rebuilds a fresh
`Score` per tier via `build_grand_staff_score(rh, lh, title=...)` **without**
forwarding `key_signature` — harmless for Spec 1 (which never detects a
key), but would silently drop the key signature on this instrumental
case's Easy/Medium tiers, since Spec 2 needs one on every tier. Building
RH/LH `Part` variants directly (mirroring `_rh_variants`/`_lh_variants`'s
existing shape) and letting the existing per-tier `build_grand_staff_score`
call in `run_arrange_pipeline`'s main loop apply `key_signature` uniformly,
exactly as it does for the non-instrumental path today, avoids that gap
entirely rather than also patching `to_easy`/`to_medium` to accept and
forward a key signature they've never needed before.

### No new modules

Everything reused here (`assign_hands`, `cap_simultaneous_notes`,
`notes_to_part`, `transcribe_audio_to_notes`) already exists and is
already imported by at least one of the two pipelines. This spec adds one
new function (`_instrumental_variants`) and one new constant/predicate
(`MIN_MELODY_NOTES`/`_is_instrumental`) to `arrange_pipeline.py`, and
changes nothing in `app/notation/`, `app/melody/`, or `app/lh/`.

## Testing

TDD as always. New coverage needed:
- `_is_instrumental`: below/at/above `MIN_MELODY_NOTES` boundary.
- `_instrumental_variants`: mocked `transcribe_audio_to_notes` output
  correctly flows through `assign_hands` → cap → `notes_to_part` →
  tier derivation; assert Easy/Medium grids and ranges match the same
  constants `_rh_variants`/`_lh_variants` use (a regression contract, not
  a new behavior).
- `run_arrange_pipeline`'s branch: a near-empty vocals stem (mocked to
  return `< MIN_MELODY_NOTES` notes) routes to `_instrumental_variants`
  instead of `_rh_variants`/`_lh_variants`; a normal vocals stem is
  unaffected (regression check that the existing pop/rock path is
  untouched).
- End-to-end `/arrange` flow with a mocked-instrumental input, confirming
  all three tiers export and all carry the detected key signature.

Real-audio verification is mandatory before calling this done, same as
every other pipeline-quality change in this project — specifically, at
least one genuinely instrumental real song (no vocals at all) run
end-to-end and listened to, both to confirm `MIN_MELODY_NOTES` doesn't
misfire on the *existing* 3-song pop/rock corpus (which must still take
the normal path unchanged) and to judge whether the DP-split RH/LH
actually sounds like a reasonable two-hand arrangement rather than just
"technically not empty."

## Tuning parameters to expect adjusting by ear

- ~~`MIN_MELODY_NOTES` (starting at 8)~~ — **superseded.** Real-audio
  verification found raw count couldn't work for any value (see the
  post-implementation update above). Shipped as `MIN_MELODY_NOTE_DENSITY`
  (`0.8` notes/second) plus `MIN_MELODY_NOTES_FOR_DENSITY_CHECK` (`2`, a
  count floor below which density is undefined) — two tunables, not one,
  and both are still validated against very little real data: 3 short
  (~45s) real-vocal clips at 1.47-2.66 notes/s, and one real ~223s
  instrumental track at 0.32 notes/s. No full-length real vocal song has
  been measured yet; a real song with a long instrumental bridge or solo
  could dilute density toward the 0.8 floor. Expect to keep tuning this as
  more real audio is tested — the routing log line
  (`backend/app/arrange_pipeline.py`) now reports note count and density
  for every job, specifically so future real jobs are free tuning data.
- Everything else (`HARD_MAX_VOICES`/`MAX_SIMULTANEOUS_VOICES_PER_HAND`,
  the difficulty grids/ranges) is inherited, already-tuned, unchanged.

## Open risk

`assign_hands`'s tunable constants are, by its own module docstring,
"hand-tuned against a handful of synthetic stress cases plus one real
~350-note transcribed **piano** clip" — this spec is the first time that
DP split runs on Basic Pitch output from a **non-piano, multi-instrument**
harmony mix (guitar/synth/strings/whatever Demucs's "other" stem contains)
rather than a real solo piano transcription. The physical hand-span and
continuity assumptions it encodes are piano-specific; whether they still
produce a sensible split when the input notes come from an ensemble mix
rather than one instrument played by two literal hands is unvalidated
and is exactly the kind of question real-audio listening verification
(above) needs to answer, not just unit tests.

**Update (2026-09-12): this risk materialized.** The one real instrumental
song tested so far (a full-band rock instrumental) produced a badly
unbalanced split: RH got 1169 notes (83% of them below MIDI 48 — bass-
register content in the "right hand"), LH got only 29 notes, all the same
pitch, sparsely scattered across the piece. This is not a reasonable
two-hand arrangement, though it is structurally valid (non-crashing,
correctly-ranged) output. Root-cause lead from the final whole-branch
review: `assign_hands` documents "a lone note at an onset is always
assigned to the right hand" as a special case — correct for solo piano,
but likely wrong for a multi-instrument mix where bass and chords land on
distinct onsets and almost every onset group has size 1, so nearly
everything defaults to RH. **Deliberately not fixed as part of this
plan** — this is Spec 1's DP tuning surface, not Spec 2's, and the fix (if
any) needs its own investigation and its own real-audio verification
pass, not a same-pass patch bolted onto this one. Routing/detection (this
spec's actual deliverable) is unaffected and works correctly; the
follow-up should be scheduled, not merely filed — for an instrumental
song, this moved the original silent-failure symptom (near-empty RH) to
near-empty LH rather than resolving it.
