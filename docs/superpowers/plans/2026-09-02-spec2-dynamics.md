# Dynamics / Expression for Spec 2 (Phase 5 quality) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the arrangement sound expressive instead of flat — by-ear
feedback (Phase 5) said it's "missing expression." Two causes: (1) Basic
Pitch already outputs a confidence/amplitude value per note
(`NoteEvent.velocity`), but nothing currently threads it into the
exported MIDI — every RH note plays at the same flat volume; (2) the
LH arrangement engine has no dynamic shaping at all — every voicing tone
in a block chord or arpeggio plays at the same volume, so nothing
distinguishes the bass/root note (which a real pianist voices more
prominently) from the inner voices.

**Architecture:** Two independent, additive changes. RH: `_to_music21_note`
(in `app/notation/hand_split.py`, shared by both Spec 1 and Spec 2) sets
`note.volume.velocityScalar` from the already-available `NoteEvent.velocity`
— this benefits **both** pipelines, since real detected dynamics are
useful information regardless of which one produced the note. LH: a
small root-vs-inner-voice velocity differential, added to
`app/arrangement/{easy,medium,hard}.py`'s note-construction — a
deterministic, rule-based accent, not derived from any audio analysis
(the LH doesn't have per-note confidence data the way Basic Pitch's
output does, since it's synthesized from chord symbols).

**Tech Stack:** Python, `music21` (existing — `note.Note().volume.velocityScalar`
is a standard music21 API, 0.0-1.0 range, same convention as `NoteEvent.velocity`).

**Spec:** No formal design doc — direct Phase 5 by-ear tuning work agreed
in conversation.

## Prerequisite: confirm your worktree has the real-tempo work merged

This plan builds directly on top of `_to_music21_note`'s current shape.
Before starting Task 1, confirm your worktree's `app/notation/hand_split.py`
already has this exact signature (run
`grep -n "_to_music21_note" backend/app/notation/hand_split.py`):

```python
def _to_music21_note(event: NoteEvent, seconds_per_quarter: float = SECONDS_PER_QUARTER) -> note.Note:
```

If it doesn't — if you instead see `_to_music21_note(event: NoteEvent) -> note.Note:`
with no second parameter — your worktree is stale. Merge in
`origin/spec-1-solo-piano-pipeline` first (`git merge origin/spec-1-solo-piano-pipeline --no-edit`),
then re-check.

## Global Constraints

- `NoteEvent.velocity` and `note.Note().volume.velocityScalar` both use
  the same `0.0-1.0` convention — direct assignment, no rescaling needed.
- The LH accent differential is a fixed, deterministic constant pair
  (not derived from audio) — consistent with the rest of the arrangement
  engine's "pure, deterministic transform" philosophy.
- This plan does not touch chord *detection* (`app/chords/`) or tempo
  threading — those are separate, parallel Phase 5 plans.

---

## File Structure

- Modify: `app/notation/hand_split.py` (`_to_music21_note`)
- Modify: `app/arrangement/theory.py` (new `ROOT_VELOCITY`/`INNER_VOICE_VELOCITY`
  constants)
- Modify: `app/arrangement/easy.py`, `medium.py`, `hard.py`
- Modify: `backend/tests/test_hand_split.py`, `test_arrangement_easy.py`,
  `test_arrangement_medium.py`, `test_arrangement_hard.py`

## Task 1: RH velocity passthrough

**Files:**
- Modify: `app/notation/hand_split.py`
- Modify: `backend/tests/test_hand_split.py`

**Interfaces:**
- Modifies: `_to_music21_note` — no signature change, just sets
  `note.volume.velocityScalar` from `event.velocity` inside the existing
  body.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_hand_split.py`:

```python
def test_notes_to_part_sets_velocity_from_the_note_event():
    notes = [NoteEvent(start=0.0, end=0.5, pitch=60, velocity=0.3)]
    part = notes_to_part(notes)
    result_note = list(part.flatten().notes)[0]
    assert result_note.volume.velocityScalar == pytest.approx(0.3)


def test_grand_staff_notes_carry_velocity_from_note_events():
    notes = [NoteEvent(start=0.0, end=0.5, pitch=60, velocity=0.9)]
    score = notes_to_grand_staff(notes)
    rh, _ = get_hand_parts(score)
    result_note = list(rh.flatten().notes)[0]
    assert result_note.volume.velocityScalar == pytest.approx(0.9)
```

Add `import pytest` at the top of the file if it isn't already imported
(check first — most test files in this repo don't need it since they
use plain `assert`, but `pytest.approx` requires the import).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_hand_split.py -v -k velocity`
Expected: FAIL — `AssertionError` comparing some default `velocityScalar`
(likely `None` or `1.0`) against the expected `0.3`/`0.9`.

- [ ] **Step 3: Write minimal implementation**

In `app/notation/hand_split.py`, add one line to `_to_music21_note` (the
signature and everything else stays exactly as-is):

```python
def _to_music21_note(event: NoteEvent, seconds_per_quarter: float = SECONDS_PER_QUARTER) -> note.Note:
    m21_note = note.Note()
    m21_note.pitch.midi = event.pitch
    m21_note.volume.velocityScalar = event.velocity
    duration = (event.end - event.start) / seconds_per_quarter
    duration = max(duration, NOTATION_GRID)
    m21_note.duration.quarterLength = _round_to_grid(duration, NOTATION_GRID)
    return m21_note
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_hand_split.py -v`
Expected: PASS (full file — confirms nothing else in this shared function
regressed for either pipeline)

- [ ] **Step 5: Commit**

```bash
git add backend/app/notation/hand_split.py backend/tests/test_hand_split.py
git commit -m "feat: propagate real note velocity into exported MIDI dynamics"
```

## Task 2: LH root-vs-inner-voice accent

**Files:**
- Modify: `app/arrangement/theory.py`
- Modify: `app/arrangement/easy.py`, `medium.py`, `hard.py`
- Modify: `backend/tests/test_arrangement_easy.py`,
  `test_arrangement_medium.py`, `test_arrangement_hard.py`

**Interfaces:**
- Produces: `ROOT_VELOCITY = 0.75`, `INNER_VOICE_VELOCITY = 0.55` in
  `app/arrangement/theory.py`.
- Modifies: `to_easy_lh`, `to_medium_lh`, `to_hard_lh` — every note now
  gets `n.volume.velocityScalar` set; the root tone (always `tones[0]`,
  since `chord_tones` returns root-first) or the Alberti pattern's root
  step (`index == 0`, i.e. the position in `tones` the pattern is
  currently playing — not the raw `step` counter) gets `ROOT_VELOCITY`,
  every other tone/step gets `INNER_VOICE_VELOCITY`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_arrangement_easy.py`:

```python
def test_easy_lh_root_note_has_root_velocity():
    chords = [ChordSymbol(start=0.0, duration=2.0, root=0, quality="major")]
    part = to_easy_lh(chords)
    n = list(part.flatten().notes)[0]
    assert n.volume.velocityScalar == pytest.approx(ROOT_VELOCITY)
```

(Add `ROOT_VELOCITY` to this file's existing import from
`app.arrangement.theory`, and `import pytest` if not already present.)

Add to `backend/tests/test_arrangement_medium.py`:

```python
def test_medium_lh_accents_the_root_over_inner_voices():
    chords = [ChordSymbol(start=0.0, duration=1.0, root=0, quality="major")]
    part = to_medium_lh(chords)
    velocities = {n.pitch.midi: n.volume.velocityScalar for n in part.flatten().notes}
    assert velocities[36] == pytest.approx(ROOT_VELOCITY)          # root, C2
    assert velocities[40] == pytest.approx(INNER_VOICE_VELOCITY)   # third, E2
    assert velocities[43] == pytest.approx(INNER_VOICE_VELOCITY)   # fifth, G2
```

(Add `ROOT_VELOCITY, INNER_VOICE_VELOCITY` to this file's existing
import from `app.arrangement.theory`, and `import pytest` if needed.)

Add to `backend/tests/test_arrangement_hard.py`:

```python
def test_hard_lh_accents_the_root_step_in_the_arpeggio():
    chords = [ChordSymbol(start=0.0, duration=3.0, root=0, quality="major")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    velocities = [n.volume.velocityScalar for n in notes[:4]]
    assert velocities == [
        pytest.approx(ROOT_VELOCITY),
        pytest.approx(INNER_VOICE_VELOCITY),
        pytest.approx(INNER_VOICE_VELOCITY),
        pytest.approx(INNER_VOICE_VELOCITY),
    ]


def test_hard_lh_accents_the_root_in_a_short_chords_block_chord():
    chords = [ChordSymbol(start=0.0, duration=0.5, root=0, quality="major")]
    part = to_hard_lh(chords)
    velocities = {n.pitch.midi: n.volume.velocityScalar for n in part.flatten().notes}
    assert velocities[36] == pytest.approx(ROOT_VELOCITY)
    assert velocities[40] == pytest.approx(INNER_VOICE_VELOCITY)
    assert velocities[43] == pytest.approx(INNER_VOICE_VELOCITY)
```

(Add `ROOT_VELOCITY, INNER_VOICE_VELOCITY` to this file's existing
import from `app.arrangement.theory`, and `import pytest` if needed.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrangement_easy.py tests/test_arrangement_medium.py tests/test_arrangement_hard.py -v -k velocity`
Expected: FAIL — `ImportError: cannot import name 'ROOT_VELOCITY'` (or
similar) since the constants don't exist yet.

- [ ] **Step 3: Write minimal implementation**

In `app/arrangement/theory.py`, add near the top (after the existing
`CHORD_INTERVALS` dict, before `chord_tones`):

```python
# A fixed, deterministic accent — not derived from any audio analysis,
# since LH notes are synthesized from chord symbols and have no
# per-note confidence data the way Basic Pitch's RH output does. Real
# pianists voice the bass/root note more prominently than inner voices;
# this is that rule, applied uniformly.
ROOT_VELOCITY = 0.75
INNER_VOICE_VELOCITY = 0.55
```

In `app/arrangement/easy.py`, add the import and one line inside the
loop:

```python
from app.arrangement.theory import ROOT_VELOCITY, pitch_class_to_midi_in_range, quantized_duration, round_to_grid
```

```python
        n = note.Note()
        n.pitch.midi = midi
        n.duration.quarterLength = length
        n.volume.velocityScalar = ROOT_VELOCITY
        part.insert(offset, n)
```

In `app/arrangement/medium.py`, add the import and one line inside the
inner loop:

```python
from app.arrangement.theory import (
    ROOT_VELOCITY,
    INNER_VOICE_VELOCITY,
    chord_tones,
    pitch_class_to_midi_in_range,
    quantized_duration,
    round_to_grid,
    stack_above,
)
```

```python
        for pitch_class in tones:
            n = note.Note()
            n.pitch.midi = stack_above(root_midi, pitch_class)
            n.duration.quarterLength = length
            n.volume.velocityScalar = ROOT_VELOCITY if pitch_class == tones[0] else INNER_VOICE_VELOCITY
            part.insert(offset, n)
```

In `app/arrangement/hard.py`, add the import and one line each in the two
note-construction sites (the short-chord block-chord branch, and the
arpeggio loop):

```python
from app.arrangement.theory import (
    ROOT_VELOCITY,
    INNER_VOICE_VELOCITY,
    chord_tones,
    pitch_class_to_midi_in_range,
    quantized_duration,
    round_to_grid,
    stack_above,
)
```

```python
        if chord.duration < SHORT_CHORD_THRESHOLD:
            offset = round_to_grid(chord.start / seconds_per_quarter)
            length = quantized_duration(chord.duration, seconds_per_quarter)
            for pitch_class in tones:
                n = note.Note()
                n.pitch.midi = stack_above(root_midi, pitch_class)
                n.duration.quarterLength = length
                n.volume.velocityScalar = ROOT_VELOCITY if pitch_class == tones[0] else INNER_VOICE_VELOCITY
                part.insert(offset, n)
            continue
```

```python
            n = note.Note()
            n.pitch.midi = stack_above(root_midi, pitch_class) + octave_lift
            n.duration.quarterLength = ARPEGGIO_STEP
            n.volume.velocityScalar = ROOT_VELOCITY if index == 0 else INNER_VOICE_VELOCITY
            part.insert(offset, n)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrangement_easy.py tests/test_arrangement_medium.py tests/test_arrangement_hard.py -v`
Expected: PASS (full contents of all three files)

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all tests pass, nothing else broken.

- [ ] **Step 6: Commit**

```bash
git add backend/app/arrangement/theory.py backend/app/arrangement/easy.py backend/app/arrangement/medium.py backend/app/arrangement/hard.py backend/tests/test_arrangement_easy.py backend/tests/test_arrangement_medium.py backend/tests/test_arrangement_hard.py
git commit -m "feat: accent the LH root note/step over inner voices"
```

## Out of Scope for This Plan

- Any further, more elaborate dynamic shaping (crescendos, phrase-level
  dynamics, accenting based on beat position within a bar rather than
  just root-vs-inner-voice) — this is a first, deliberately simple pass;
  revisit after by-ear feedback on this round.
- Chord-detection key-awareness and richer arrangement texture —
  separate, parallel/later Phase 5 plans.
