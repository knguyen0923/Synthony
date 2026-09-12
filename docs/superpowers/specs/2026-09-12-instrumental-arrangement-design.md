# Instrumental Arrangement Design (Track 3, Phase 1)

## Motivation

Spec 2's `/arrange` pipeline hard-wires four Demucs stems to two fixed
roles: `vocals` becomes RH (forced monophonic via
`melody.extract.reduce_to_monophonic`), `bass`+`other` becomes LH. This
was explicitly deferred scope from the original Spec 2 design (see that
doc's "Phase 6 (later, separate spec) — Broaden beyond pop/rock" note):
instrumentals, rap, orchestral, and multi-melody songs all break this
assumption in different ways.

A research pass (this session) found the four cases don't share one
fix. Instrumentals and orchestral share a root cause — no single "the
melody" exists to isolate onto a vocals stem — and a shared candidate
fix: bypass the stem-role split entirely and reuse Spec 1's
already-working, already-tested continuity-aware DP hand-split
(`notation/hand_assignment.assign_hands`, invoked via
`notation.hand_split.notes_to_grand_staff`). Rap and multi-melody are a
different problem (the transcription model itself can't represent the
content, or two independently valid melodies exist at once) needing new
capability, not reuse — deliberately out of scope here, to be
brainstormed as a separate spec later.

This is Phase 1 of that split: **instrumentals only**. Orchestral is
deferred past this phase — it stacks a second, independent risk on top
(Demucs's stem categories don't match orchestral instrumentation at
all, and *no* transcription model here has been validated on full
orchestral mixes), and narrowing to the easier case first lets the
shared architecture (bypass stem-split, reuse Spec 1's DP) get proven
before betting a spec on the harder one.

## Current State (for reference)

- `arrange_pipeline.run_arrange_pipeline`: after `separate_stems`,
  unconditionally calls `extract_melody_notes(str(stems.vocals))` for
  RH and `mix_wav_files(stems.bass, stems.other, ...)` +
  `extract_lh_notes(harmony_path)` for LH. No branching exists on
  whether the vocals stem actually contains anything.
- For a track with no vocal content, Demucs's vocals stem is near-silent
  (noise floor / faint leakage, not a clean zero). `extract_melody_notes`
  runs Basic Pitch on it anyway; `reduce_to_monophonic` then returns
  either an empty list or a scatter of spurious low-confidence notes.
  Today this produces a **silent, undetected failure** — RH comes out
  empty or musically nonsensical, with no error surfaced anywhere.
- `notation.hand_assignment.assign_hands(notes) -> (rh_notes, lh_notes)`:
  the continuity-aware DP search (span, continuity, crossing, switching
  costs — see that module's docstring) already used by Spec 1
  (`/transcribe`) to split one polyphonic transcription into two hands
  with no predetermined melody/harmony source. This is genre-agnostic —
  it operates purely on note timing/pitch, with no assumption about
  what instrument produced the audio.
- `notation.hand_split.notes_to_grand_staff(notes, title, beat_map,
  pedal_events) -> stream.Score`: calls `assign_hands`, caps each hand to
  `MAX_SIMULTANEOUS_VOICES_PER_HAND` via `voice_cap.cap_simultaneous_notes`,
  builds both `stream.Part`s, and assembles the full grand-staff Score
  (clefs, key signature via a separate step, piano brace) — this is Spec
  1's exact Hard-tier construction, already used by `main.py`'s
  `/transcribe` endpoint.
- `difficulty.engine.generate_variants(score) -> DifficultyVariants`:
  Spec 1's exact difficulty engine (`to_easy`/`to_medium`/`to_hard` from
  `difficulty/easy.py`, `medium.py`, `hard.py`), operating on a full
  grand-staff `Score` via `get_hand_parts`/`build_grand_staff_score`, not
  on the RH/LH-specific variant builders `arrange_pipeline.py` uses today
  (`_rh_variants`/`_lh_variants`, which assume the vocals-monophonic /
  bass+other-polyphonic split).
- `transcription.audio_to_midi.transcribe_audio_to_notes(audio_path) ->
  list[NoteEvent]`: the shared raw Basic Pitch call already used by both
  `melody.extract.extract_melody_notes` (vocals, then reduced to
  monophonic) and `lh.extract.extract_lh_notes` (harmony mix, then capped
  to `HARD_MAX_VOICES`).

## New Architecture

```
stems = separate_stems(audio_path)  [unchanged]
  │
  ▼
is_instrumental(stems.vocals)?  [NEW — see Detection below]
  │
  ├─ no (has vocals) ──────────► existing path, unchanged:
  │                              extract_melody_notes(vocals) → RH
  │                              mix_wav_files(bass, other) → extract_lh_notes → LH
  │                              _rh_variants / _lh_variants (arrange_pipeline.py)
  │
  └─ yes (instrumental) ───────► NEW path:
       mix_wav_files(bass, other) → harmony.wav        [reused as-is, same call already made for key/tempo detection]
       transcribe_audio_to_notes(harmony.wav) → notes  [reused as-is — no monophonic reduction, no voice cap: full polyphonic transcription]
       notes_to_grand_staff(notes, title, beat_map) → score   [reused as-is — Spec 1's exact DP hand-split + assembly]
       generate_variants(score) → {easy, medium, hard} [reused as-is — Spec 1's exact difficulty engine]
```

Everything on the instrumental path is existing, already-tested Spec 1
machinery. The only genuinely new code is the detection check and the
routing branch in `run_arrange_pipeline` itself — no new note-processing
logic, no new difficulty-derivation logic.

Key/tempo detection (`detect_key_and_tempo`, `detect_beat_map`) already
runs on the same `harmony.wav` regardless of branch, so it's unaffected
by this change — both branches can compute it identically, before or
after the branch point.

## Detection

`is_instrumental(vocals_path: str) -> bool` in a new module,
`app/arrange_pipeline.py`-adjacent (e.g. `app/vocals/detect.py`):
measure the isolated vocals stem's RMS energy relative to the full
pre-separation mix. Below a tuned threshold, classify as instrumental.

RMS energy (not a Basic Pitch note-yield check) is the primary signal:
it's a cheap numeric computation on the waveform, not a second ML model
invocation, so a track that turns out to have vocals doesn't pay an
extra Basic Pitch call just to be classified.

This is a first-pass heuristic, not a solved classification problem.
Known, accepted limitation: quiet/whispered vocals could be
misclassified as instrumental, and a sparse/faint instrumental could in
principle be misclassified as vocal. The threshold needs tuning against
real audio (see Testing), and misclassification is a documented
limitation to revisit if real listening surfaces it as an actual
problem — not something this phase claims to fully solve.

## Components

### `app/vocals/detect.py` (new)

```python
def is_instrumental(vocals_path: str, mix_path: str, threshold: float = VOCALS_ENERGY_THRESHOLD) -> bool:
    """RMS energy of the isolated vocals stem, relative to the
    pre-separation mix, below `threshold` classifies the track as
    instrumental (no meaningful vocal content) — routes /arrange to the
    Spec-1-reuse path instead of the vocals-as-RH path. A first-pass
    heuristic (see design doc's Detection section on its known
    false-positive/negative risk), not a definitive classifier."""
```

`VOCALS_ENERGY_THRESHOLD` starts as a tuning constant, expected to be
adjusted by ear/measurement once real instrumental + vocal test audio is
in hand (see Tuning below) — no principled starting value exists yet.

### `arrange_pipeline.py` (modified)

```python
def run_arrange_pipeline(...):
    ...
    stems = separate_stems(audio_path, dest_dir / "stems")
    harmony_path = mix_wav_files(stems.bass, stems.other, dest_dir / "stems" / "harmony.wav")
    detected_key, seconds_per_quarter = detect_key_and_tempo(str(harmony_path))
    beat_map = detect_beat_map(str(harmony_path))
    key_signature = key_signature_from_tonic(*detected_key)

    if is_instrumental(str(stems.vocals), audio_path):
        set_status(job_id, "arranging")
        notes = transcribe_audio_to_notes(str(harmony_path))
        if not notes:
            raise ValueError("No pitched content detected")
        score = notes_to_grand_staff(notes, title=title, beat_map=beat_map)
        # notes_to_grand_staff doesn't take a key signature — apply it
        # the same way Spec 1's /transcribe endpoint would need to if it
        # used one; simplest: insert into rh/lh via get_hand_parts before
        # generate_variants, mirroring build_grand_staff_score's existing
        # key_signature parameter.
        variants = generate_variants(score)
        difficulties = {
            tier: _export(variant, tier) for tier, variant in
            (("easy", variants.easy), ("medium", variants.medium), ("hard", variants.hard))
        }
    else:
        # existing vocals-as-RH path, unchanged
        ...
```

The exact key-signature wiring (`notes_to_grand_staff` doesn't accept
one directly, unlike `build_grand_staff_score`) is an implementation
detail for the plan/implementation phase, not a design-level decision —
noted here so it isn't missed, not resolved here.

## Testing

Matches this project's existing TDD + real-audio-verification norms:

- `is_instrumental`: unit tests with synthetic near-silent vs. energetic
  waveforms: clearly-instrumental and clearly-vocal cases pass at
  whatever starting threshold is chosen; document that the boundary
  itself is untested by unit tests (it can only be tuned against real
  audio).
- Routing logic in `run_arrange_pipeline`: unit test that each branch is
  taken given a mocked `is_instrumental` return value, and that the
  instrumental branch calls `transcribe_audio_to_notes` +
  `notes_to_grand_staff` + `generate_variants` (not
  `extract_melody_notes`/`_rh_variants`/`_lh_variants`).
- No new tests needed for `assign_hands`, `notes_to_grand_staff`,
  `generate_variants`, or `transcribe_audio_to_notes` themselves — all
  reused unchanged, already covered by Spec 1's existing test suite.
- Real-audio verification: add at least one genuinely instrumental track
  to the local verification corpus (today's corpus is 1 solo piano + 3
  full songs, all with vocals). Per this project's established practice,
  scope the actual listening check to the **Hard tier only**. This
  verification is where `VOCALS_ENERGY_THRESHOLD` gets tuned — there is
  no way to pick a real starting value without it.

## Tuning parameters to expect adjusting by ear

- `VOCALS_ENERGY_THRESHOLD` — no principled starting value; set from the
  first real instrumental-track verification pass.
- `MAX_SIMULTANEOUS_VOICES_PER_HAND` (from `hand_split.py`, already `4`)
  — reused as-is, but instrumental audio's spectral content differs from
  solo piano; may need its own value if listening surfaces over/under
  capping specific to this new input type.

## Open risks

- **Detection is a heuristic, not a classifier.** See Detection section
  above — false positives/negatives are expected and accepted for this
  phase, to be revisited only if real listening surfaces them as an
  actual problem.
- **No lead-instrument protection.** Unlike the vocals-as-RH path, which
  guarantees a sung melody becomes RH, the DP hand-split has no concept
  of "this is the lead line, protect it" — it splits by physical
  hand-span/continuity only. An instrumental with one clear lead
  instrument (a guitar hook, a synth lead) may have that line correctly
  land in RH by the DP's own continuity logic, or may not, depending on
  the piece's texture. This phase does not add lead-instrument detection
  — it's an open question for a later phase if listening shows the DP's
  generic split under-serves the common "one obvious lead instrument"
  case specifically.
- **Basic Pitch on non-piano instrumental audio is unvalidated.** Basic
  Pitch already runs on Demucs's "other"/bass stems today for Spec 2's
  LH, so this isn't a wholly new risk — but running it as the *sole*
  transcription source for a full instrumental arrangement (not just
  accompaniment) is higher-stakes than before, and hasn't been
  specifically evaluated. Real-audio verification against a genuine
  instrumental track is where this gets checked, not before.
