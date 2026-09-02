# Arrangement Engine (Spec 2, Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure `chord sequence -> Part` arrangement engine that turns a
detected chord sequence into a left-hand piano part, one pattern style per
difficulty tier (root notes / block chords / Alberti-bass arpeggio).

**Architecture:** A new `backend/app/arrangement/` package, structured like
the existing `backend/app/difficulty/` package: small, pure, hand-testable
functions operating on `music21` `stream.Part` objects. No ML, no external
services — deterministic music-theory transforms only. This package does not
depend on chord *recognition* (Phase 2) or melody *extraction* (Phase 1) —
it only consumes a `ChordSymbol` sequence, a data type this plan defines, so
it is buildable and testable today against hand-crafted chord sequences.

**Tech Stack:** Python, `music21` (already a dependency), `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-01-any-song-arrangement-design.md`
(see "New Components" → Arrangement engine, "Phased Roadmap" → Phase 3,
"Testing Strategy" → Arrangement engine, and "Key Decisions Log" →
"Chord-symbol arrangement, not stem-transcription reuse").

## Global Constraints

- Deterministic, non-ML, pure functions only — no training data, no
  external calls (per spec's "Deterministic, non-ML arrangement and chord
  recognition" decision).
- Pattern varies by difficulty tier: root notes only for Easy, block chords
  for Medium, arpeggiated/Alberti-bass for Hard (per spec's Phase 3).
- Structured like `difficulty/easy.py` / `medium.py` / `hard.py`: small,
  independently unit-testable functions, one file per tier (per spec's
  "New Components" → Arrangement engine).
- Time values follow the codebase's existing fixed-tempo assumption:
  `SECONDS_PER_QUARTER = 0.5` (120 BPM), imported from
  `app.notation.hand_split` rather than redefined, so this module can never
  drift from the rest of the pipeline's tempo assumption.
- LH pitch ranges mirror the existing difficulty tiers' LH ranges
  (`backend/app/difficulty/easy.py`'s `EASY_LH_RANGE = (36, 48)`,
  `medium.py`'s `MEDIUM_LH_RANGE = (36, 55)`) so arrangement output sits in
  the same register the rest of the app already assumes is playable.
- Tests use hand-crafted `ChordSymbol` sequences with exact expected
  output, per the spec's Testing Strategy for the arrangement engine.

---

## File Structure

- Create: `backend/app/arrangement/__init__.py` (empty, package marker)
- Create: `backend/app/arrangement/types.py` — `ChordSymbol` dataclass
- Create: `backend/app/arrangement/theory.py` — chord-quality interval
  table and pitch-placement helpers shared by all three tiers
- Create: `backend/app/arrangement/easy.py` — `to_easy_lh`
- Create: `backend/app/arrangement/medium.py` — `to_medium_lh`
- Create: `backend/app/arrangement/hard.py` — `to_hard_lh`
- Create: `backend/app/arrangement/engine.py` — `ArrangementVariants`,
  `generate_lh_variants`
- Create: `backend/tests/test_arrangement_theory.py`
- Create: `backend/tests/test_arrangement_easy.py`
- Create: `backend/tests/test_arrangement_medium.py`
- Create: `backend/tests/test_arrangement_hard.py`
- Create: `backend/tests/test_arrangement_engine.py`

## Task 1: Chord data type and music-theory helpers

**Files:**
- Create: `backend/app/arrangement/types.py`
- Create: `backend/app/arrangement/theory.py`
- Test: `backend/tests/test_arrangement_theory.py`

**Interfaces:**
- Produces: `ChordSymbol(start: float, duration: float, root: int, quality: str)`
  — `start`/`duration` in seconds (matches `NoteEvent`'s convention in
  `app/notation/types.py`); `root` is a pitch class 0-11 (0=C); `quality` is
  one of `"major"`, `"minor"`, `"dim"`, `"dom7"`, `"maj7"`, `"min7"`.
- Produces: `chord_tones(root: int, quality: str) -> list[int]` — pitch
  classes (0-11), root first.
- Produces: `pitch_class_to_midi_in_range(pitch_class: int, low: int, high: int) -> int`
- Produces: `stack_above(base_midi: int, pitch_class: int) -> int`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_arrangement_theory.py
from app.arrangement.theory import (
    chord_tones,
    pitch_class_to_midi_in_range,
    stack_above,
)


def test_chord_tones_major():
    assert chord_tones(0, "major") == [0, 4, 7]  # C major: C E G


def test_chord_tones_min7_wraps_pitch_class():
    assert chord_tones(2, "min7") == [2, 5, 9, 0]  # Dmin7: D F A C


def test_pitch_class_to_midi_in_range_shifts_up_and_down():
    assert pitch_class_to_midi_in_range(0, 36, 48) == 36  # C -> C2
    assert pitch_class_to_midi_in_range(11, 36, 48) == 47  # B -> B2


def test_stack_above_finds_nearest_instance_at_or_above_base():
    assert stack_above(36, 4) == 40  # E above C2 -> E2
    assert stack_above(36, 0) == 36  # same pitch class as base, no shift needed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_arrangement_theory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.arrangement'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/arrangement/types.py
from dataclasses import dataclass


@dataclass(frozen=True)
class ChordSymbol:
    start: float       # seconds
    duration: float     # seconds
    root: int           # pitch class, 0=C .. 11=B
    quality: str         # one of theory.CHORD_INTERVALS' keys
```

```python
# backend/app/arrangement/theory.py
CHORD_INTERVALS: dict[str, tuple[int, ...]] = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "dim": (0, 3, 6),
    "dom7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
}


def chord_tones(root: int, quality: str) -> list[int]:
    """Pitch classes (0-11), root first, that make up the chord."""
    return [(root + interval) % 12 for interval in CHORD_INTERVALS[quality]]


def pitch_class_to_midi_in_range(pitch_class: int, low: int, high: int) -> int:
    """Lowest MIDI number with the given pitch class that falls within
    [low, high]."""
    midi = pitch_class
    while midi < low:
        midi += 12
    while midi > high:
        midi -= 12
    return midi


def stack_above(base_midi: int, pitch_class: int) -> int:
    """Smallest MIDI number >= base_midi with the given pitch class —
    voices a chord tone in close position above an anchor note."""
    midi = pitch_class + 12 * (base_midi // 12)
    while midi < base_midi:
        midi += 12
    return midi
```

- [ ] **Step 4: Create the package marker**

```bash
touch backend/app/arrangement/__init__.py
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_arrangement_theory.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/arrangement/__init__.py backend/app/arrangement/types.py backend/app/arrangement/theory.py backend/tests/test_arrangement_theory.py
git commit -m "feat: add ChordSymbol type and chord-theory helpers for arrangement engine"
```

## Task 2: Easy tier — root notes only

**Files:**
- Create: `backend/app/arrangement/easy.py`
- Test: `backend/tests/test_arrangement_easy.py`

**Interfaces:**
- Consumes: `ChordSymbol` (Task 1), `pitch_class_to_midi_in_range` (Task 1),
  `SECONDS_PER_QUARTER` from `app.notation.hand_split`.
- Produces: `to_easy_lh(chords: list[ChordSymbol]) -> stream.Part` — a
  `music21` Part with id `"LH"`, one note per chord (its root, in-range),
  held for the chord's full duration.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_arrangement_easy.py
from app.arrangement.easy import to_easy_lh
from app.arrangement.types import ChordSymbol


def test_easy_lh_holds_root_for_full_chord_duration():
    chords = [ChordSymbol(start=0.0, duration=2.0, root=0, quality="major")]
    part = to_easy_lh(chords)
    notes = list(part.flatten().notes)
    assert len(notes) == 1
    assert notes[0].pitch.midi == 36  # C2, nearest C within (36, 48)
    assert notes[0].duration.quarterLength == 4.0  # 2s / 0.5s-per-quarter


def test_easy_lh_places_each_chord_at_its_own_offset():
    chords = [
        ChordSymbol(start=0.0, duration=1.0, root=0, quality="major"),
        ChordSymbol(start=1.0, duration=1.0, root=7, quality="major"),
    ]
    part = to_easy_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    assert [n.offset for n in notes] == [0.0, 2.0]
    assert notes[1].pitch.midi == 43  # G2, nearest G within (36, 48)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_arrangement_easy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.arrangement.easy'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/arrangement/easy.py
from music21 import clef, note, stream

from app.arrangement.theory import pitch_class_to_midi_in_range
from app.arrangement.types import ChordSymbol
from app.notation.hand_split import SECONDS_PER_QUARTER

EASY_LH_RANGE = (36, 48)  # C2-C3, matches difficulty/easy.py's LH range


def to_easy_lh(chords: list[ChordSymbol]) -> stream.Part:
    """One root note per chord, held for the chord's full duration."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    for chord in chords:
        offset = chord.start / SECONDS_PER_QUARTER
        length = chord.duration / SECONDS_PER_QUARTER
        midi = pitch_class_to_midi_in_range(chord.root, *EASY_LH_RANGE)
        n = note.Note()
        n.pitch.midi = midi
        n.duration.quarterLength = length
        part.insert(offset, n)
    return part
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_arrangement_easy.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/arrangement/easy.py backend/tests/test_arrangement_easy.py
git commit -m "feat: add Easy-tier arrangement (root-note LH)"
```

## Task 3: Medium tier — close-position block chords

**Files:**
- Create: `backend/app/arrangement/medium.py`
- Test: `backend/tests/test_arrangement_medium.py`

**Interfaces:**
- Consumes: `ChordSymbol`, `chord_tones`, `pitch_class_to_midi_in_range`,
  `stack_above` (Task 1), `SECONDS_PER_QUARTER`.
- Produces: `to_medium_lh(chords: list[ChordSymbol]) -> stream.Part` — a
  block chord (root + third + fifth, 7th dropped for playability) per
  chord, held for the chord's full duration.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_arrangement_medium.py
from app.arrangement.medium import to_medium_lh
from app.arrangement.types import ChordSymbol


def test_medium_lh_voices_a_close_position_triad():
    chords = [ChordSymbol(start=0.0, duration=1.0, root=0, quality="major")]
    part = to_medium_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.pitch.midi)
    assert [n.pitch.midi for n in notes] == [36, 40, 43]  # C2, E2, G2


def test_medium_lh_drops_the_seventh_to_stay_a_triad():
    chords = [ChordSymbol(start=0.0, duration=1.0, root=0, quality="dom7")]
    part = to_medium_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.pitch.midi)
    assert len(notes) == 3
    assert [n.pitch.midi for n in notes] == [36, 40, 43]  # root/3rd/5th only
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_arrangement_medium.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.arrangement.medium'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/arrangement/medium.py
from music21 import clef, note, stream

from app.arrangement.theory import chord_tones, pitch_class_to_midi_in_range, stack_above
from app.arrangement.types import ChordSymbol
from app.notation.hand_split import SECONDS_PER_QUARTER

MEDIUM_LH_RANGE = (36, 55)  # C2-G3, matches difficulty/medium.py's LH range
MAX_BLOCK_TONES = 3  # root + third + fifth; drop the 7th for playability


def to_medium_lh(chords: list[ChordSymbol]) -> stream.Part:
    """A close-position block chord (root + third + fifth) per chord,
    held for the chord's full duration."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    for chord in chords:
        offset = chord.start / SECONDS_PER_QUARTER
        length = chord.duration / SECONDS_PER_QUARTER
        tones = chord_tones(chord.root, chord.quality)[:MAX_BLOCK_TONES]
        root_midi = pitch_class_to_midi_in_range(tones[0], *MEDIUM_LH_RANGE)
        for pitch_class in tones:
            n = note.Note()
            n.pitch.midi = stack_above(root_midi, pitch_class)
            n.duration.quarterLength = length
            part.insert(offset, n)
    return part
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_arrangement_medium.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/arrangement/medium.py backend/tests/test_arrangement_medium.py
git commit -m "feat: add Medium-tier arrangement (block-chord LH)"
```

## Task 4: Hard tier — Alberti-bass arpeggio, and the variant-generation entry point

**Files:**
- Create: `backend/app/arrangement/hard.py`
- Create: `backend/app/arrangement/engine.py`
- Test: `backend/tests/test_arrangement_hard.py`
- Test: `backend/tests/test_arrangement_engine.py`

**Interfaces:**
- Consumes: `ChordSymbol`, `chord_tones`, `pitch_class_to_midi_in_range`,
  `stack_above` (Task 1), `SECONDS_PER_QUARTER`, `to_easy_lh` (Task 2),
  `to_medium_lh` (Task 3).
- Produces: `to_hard_lh(chords: list[ChordSymbol]) -> stream.Part` — a
  root-fifth-third-fifth Alberti arpeggio, subdivided into eighth notes
  across each chord's duration.
- Produces: `ArrangementVariants(easy: stream.Part, medium: stream.Part, hard: stream.Part)`
  and `generate_lh_variants(chords: list[ChordSymbol]) -> ArrangementVariants`
  — the package's public entry point, mirroring
  `difficulty/engine.py`'s `DifficultyVariants` / `generate_variants`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_arrangement_hard.py
from app.arrangement.hard import to_hard_lh
from app.arrangement.types import ChordSymbol


def test_hard_lh_arpeggiates_root_then_fifth_across_one_beat():
    # duration=0.5s = 1 quarter note = 2 eighth-note arpeggio steps
    chords = [ChordSymbol(start=0.0, duration=0.5, root=0, quality="major")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    assert [n.offset for n in notes] == [0.0, 0.5]
    assert [n.pitch.midi for n in notes] == [36, 43]  # root(C2), fifth(G2)


def test_hard_lh_continues_alberti_pattern_into_third_and_fourth_steps():
    # duration=1.0s = 2 quarter notes = 4 eighth-note arpeggio steps
    chords = [ChordSymbol(start=0.0, duration=1.0, root=0, quality="major")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    assert [n.pitch.midi for n in notes] == [36, 43, 40, 43]  # root, 5th, 3rd, 5th
```

```python
# backend/tests/test_arrangement_engine.py
from app.arrangement.engine import generate_lh_variants
from app.arrangement.types import ChordSymbol


def test_generate_lh_variants_produces_all_three_tiers():
    chords = [ChordSymbol(start=0.0, duration=1.0, root=0, quality="major")]
    variants = generate_lh_variants(chords)
    assert len(list(variants.easy.flatten().notes)) == 1
    assert len(list(variants.medium.flatten().notes)) == 3
    assert len(list(variants.hard.flatten().notes)) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_arrangement_hard.py tests/test_arrangement_engine.py -v`
Expected: FAIL with `ModuleNotFoundError` for `app.arrangement.hard` / `app.arrangement.engine`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/arrangement/hard.py
from music21 import clef, note, stream

from app.arrangement.theory import chord_tones, pitch_class_to_midi_in_range, stack_above
from app.arrangement.types import ChordSymbol
from app.notation.hand_split import SECONDS_PER_QUARTER

HARD_LH_RANGE = (36, 55)  # C2-G3, same bass register as the Medium tier
ARPEGGIO_STEP = 0.5  # eighth note, in quarterLength units
# Classic Alberti-bass order: root, fifth, third, fifth (indices into
# chord_tones()'s root-first ordering). The inner `% len(tones)` handles
# chords with fewer tones than the pattern references.
ALBERTI_INDICES = (0, 2, 1, 2)


def to_hard_lh(chords: list[ChordSymbol]) -> stream.Part:
    """An Alberti-bass arpeggio (root-fifth-third-fifth) per chord,
    subdivided into eighth notes across the chord's duration."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    step_seconds = ARPEGGIO_STEP * SECONDS_PER_QUARTER

    for chord in chords:
        tones = chord_tones(chord.root, chord.quality)
        root_midi = pitch_class_to_midi_in_range(tones[0], *HARD_LH_RANGE)

        step = 0
        elapsed = 0.0
        while elapsed < chord.duration:
            index = ALBERTI_INDICES[step % len(ALBERTI_INDICES)] % len(tones)
            pitch_class = tones[index]
            offset = (chord.start + elapsed) / SECONDS_PER_QUARTER

            n = note.Note()
            n.pitch.midi = stack_above(root_midi, pitch_class)
            n.duration.quarterLength = ARPEGGIO_STEP
            part.insert(offset, n)

            step += 1
            elapsed += step_seconds

    return part
```

```python
# backend/app/arrangement/engine.py
from dataclasses import dataclass

from music21 import stream

from app.arrangement.easy import to_easy_lh
from app.arrangement.hard import to_hard_lh
from app.arrangement.medium import to_medium_lh
from app.arrangement.types import ChordSymbol


@dataclass
class ArrangementVariants:
    easy: stream.Part
    medium: stream.Part
    hard: stream.Part


def generate_lh_variants(chords: list[ChordSymbol]) -> ArrangementVariants:
    return ArrangementVariants(
        easy=to_easy_lh(chords),
        medium=to_medium_lh(chords),
        hard=to_hard_lh(chords),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_arrangement_hard.py tests/test_arrangement_engine.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full arrangement test suite**

Run: `cd backend && python -m pytest tests/test_arrangement_theory.py tests/test_arrangement_easy.py tests/test_arrangement_medium.py tests/test_arrangement_hard.py tests/test_arrangement_engine.py -v`
Expected: PASS (11 tests total)

- [ ] **Step 6: Commit**

```bash
git add backend/app/arrangement/hard.py backend/app/arrangement/engine.py backend/tests/test_arrangement_hard.py backend/tests/test_arrangement_engine.py
git commit -m "feat: add Hard-tier Alberti-bass arrangement and generate_lh_variants entry point"
```

## Out of Scope for This Plan

- Wiring `generate_lh_variants` into an HTTP endpoint or the storage
  layer — that's Phase 4 (async job infra), which also needs the melody
  (RH) side from Phase 1 to build a full grand-staff `Score`.
- Actual chord *recognition* from audio (Phase 2) — this plan only
  consumes `ChordSymbol` sequences however they're constructed (by hand in
  tests here, later by Phase 2's detector).
- Combining this LH output with a Phase-1-produced RH `Part` via
  `build_grand_staff_score` — left for whichever plan wires Phases 1-3
  together, since Phase 1 (melody/RH) doesn't exist yet.
