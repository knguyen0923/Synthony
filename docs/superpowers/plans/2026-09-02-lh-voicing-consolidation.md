# LH Voicing Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the LH (left-hand) arrangement's Easy/Medium/Hard difficulty tiers provably *derive* their chord tones from one shared function, instead of each independently calling `chord_tones()` and picking its own subset — closing the architectural gap called out in `docs/superpowers/plans/2026-09-01-arrangement-engine.md`'s follow-up notes, where RH's Easy/Medium already derive from one rich base (`quantize_part`/`shift_into_range` over `build_melody_part`'s output) but LH's three tiers were built as three separately-authored files.

**Architecture:** Add one function, `lh_voicing(chord, seconds_per_quarter) -> (tones, is_short)`, to `app/arrangement/theory.py`. It returns the same root-first tone list `chord_tones()` already computes, plus the short/long classification Hard uses to decide block-chord-vs-arpeggio. All three tier files (`easy.py`, `medium.py`, `hard.py`) call this one function instead of computing tones themselves — Easy takes `tones[0]`, Medium takes `tones[:MAX_BLOCK_TONES]`, Hard takes the full list and `is_short`. This is a pure refactor: every existing arrangement test must still pass unchanged, because the musical output (what notes render, in what register, at what velocity) is not changing — only where the tone-selection logic lives.

**Tech Stack:** Python, music21, pytest (existing stack — no new dependencies).

**Spec:** `docs/superpowers/plans/2026-09-01-arrangement-engine.md` (original LH design); this plan implements the consolidation follow-up agreed in that work, not a new design.

## Global Constraints

- Zero behavior change to rendered MusicXML/MIDI output for any of the 3 tiers — this is a structural refactor, not a musical one. Every existing test in `test_arrangement_easy.py`, `test_arrangement_medium.py`, `test_arrangement_hard.py`, and `test_arrangement_engine.py` must pass without modifying their assertions (only import-line changes are allowed, and only where noted below).
- Do not touch `to_hard_lh`'s arpeggio/octave-lift/block-chord musical logic — only how it obtains `tones` and the short/long classification.
- Do not invent new musical patterns (voice-leading, walking bass, syncopation). That's explicitly out of scope for this plan — it's a separate, ear-judgment-driven initiative for later.
- Follow this repo's TDD discipline: write the failing test, verify the exact failure, implement, verify green, commit — for every step below.

---

### Task 1: Add `short_chord_threshold` and `lh_voicing` to `theory.py`

**Files:**
- Modify: `backend/app/arrangement/theory.py`
- Test: `backend/tests/test_arrangement_theory.py`

**Interfaces:**
- Consumes: `ChordSymbol` from `app.arrangement.types` (new import into theory.py — no circular dependency; `types.py` imports nothing from `arrangement`).
- Produces (for Tasks 2 and 3):
  - `SHORT_CHORD_QUARTER_LENGTH: float` (module constant, value `6.0`, moved from `hard.py`)
  - `short_chord_threshold(seconds_per_quarter: float) -> float`
  - `lh_voicing(chord: ChordSymbol, seconds_per_quarter: float) -> tuple[list[int], bool]` — returns `(tones, is_short)` where `tones == chord_tones(chord.root, chord.quality)` and `is_short == (chord.duration < short_chord_threshold(seconds_per_quarter))`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_arrangement_theory.py`:

```python
from app.arrangement.theory import (
    chord_tones,
    lh_voicing,
    pitch_class_to_midi_in_range,
    short_chord_threshold,
    stack_above,
)
from app.arrangement.types import ChordSymbol
```

Replace the existing `from app.arrangement.theory import (...)` import block at the top of the file with the block above (adds `lh_voicing`, `short_chord_threshold`, and the new `ChordSymbol` import).

Then append these tests at the end of the file:

```python
def test_short_chord_threshold_is_one_and_a_half_bars_at_the_given_tempo():
    import pytest
    seconds_per_quarter = 0.5
    assert short_chord_threshold(seconds_per_quarter) == pytest.approx(6.0 * 0.5)


def test_short_chord_threshold_scales_with_tempo():
    fast_tempo = short_chord_threshold(60.0 / 129.2)
    slow_tempo = short_chord_threshold(60.0 / 73.8)
    assert slow_tempo > fast_tempo


def test_lh_voicing_returns_chord_tones_root_first():
    chord = ChordSymbol(start=0.0, duration=1.0, root=2, quality="min7")
    tones, _ = lh_voicing(chord, seconds_per_quarter=0.5)
    assert tones == chord_tones(2, "min7")


def test_lh_voicing_is_short_below_threshold():
    chord = ChordSymbol(start=0.0, duration=0.5, root=0, quality="major")
    _, is_short = lh_voicing(chord, seconds_per_quarter=0.5)
    assert is_short is True


def test_lh_voicing_is_not_short_at_or_above_threshold():
    chord = ChordSymbol(start=0.0, duration=6.0, root=0, quality="major")
    _, is_short = lh_voicing(chord, seconds_per_quarter=1.0)
    assert is_short is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrangement_theory.py -v`
Expected: FAIL — `ImportError: cannot import name 'lh_voicing'` (and `short_chord_threshold`) from `app.arrangement.theory`.

- [ ] **Step 3: Implement in theory.py**

Add near the top of `backend/app/arrangement/theory.py`, after the existing imports (add `from app.arrangement.types import ChordSymbol`):

```python
# A chord shorter than this (tempo-relative, not a fixed number of
# seconds) gets a single block-chord hit (full tone set, including the
# 7th) instead of an arpeggio — an Alberti pattern chopped off partway
# through a short chord reads worse than one clean stab. 1.5 bars in 4/4
# (matches this codebase's fixed-4/4 assumption). A fixed-seconds
# threshold made this split accidentally tempo-dependent: a slow song's
# bars were all longer than the fixed cutoff (100% arpeggio, zero
# block-chord variety), while a fast song's threshold happened to land
# almost exactly between its 1-bar and 2-bar chords purely by
# coincidence (found via real-song testing).
SHORT_CHORD_QUARTER_LENGTH = 6.0


def short_chord_threshold(seconds_per_quarter: float) -> float:
    """Real-seconds duration below which a chord is "short" (gets a block
    chord instead of an arpeggio) at the given tempo — 1.5 bars."""
    return SHORT_CHORD_QUARTER_LENGTH * seconds_per_quarter


def lh_voicing(chord: ChordSymbol, seconds_per_quarter: float) -> tuple[list[int], bool]:
    """The tones (pitch classes, root first) and short/long classification
    every LH difficulty tier is built from for one chord — the single
    source Easy/Medium/Hard all read from, so their tone choices are
    provably derived from one place rather than three independently
    authored ones. `is_short` mirrors Hard's block-chord-vs-arpeggio
    split; Easy and Medium ignore it and always render a static block."""
    tones = chord_tones(chord.root, chord.quality)
    is_short = chord.duration < short_chord_threshold(seconds_per_quarter)
    return tones, is_short
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrangement_theory.py -v`
Expected: PASS (all tests, including pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add backend/app/arrangement/theory.py backend/tests/test_arrangement_theory.py
git commit -m "feat: add shared lh_voicing() as the single LH tone-selection source"
```

---

### Task 2: Refactor `hard.py` to use `lh_voicing`

**Files:**
- Modify: `backend/app/arrangement/hard.py`
- Modify: `backend/tests/test_arrangement_hard.py` (import line only)

**Interfaces:**
- Consumes: `lh_voicing`, `short_chord_threshold` from `app.arrangement.theory` (Task 1).
- Produces: `to_hard_lh` unchanged in signature and output; `_short_chord_threshold` and `SHORT_CHORD_QUARTER_LENGTH` no longer exist in `hard.py` (moved to `theory.py` in Task 1).

- [ ] **Step 1: Update the test import (this is the "failing test" step for a pure refactor)**

In `backend/tests/test_arrangement_hard.py`, replace:

```python
from app.arrangement.hard import _short_chord_threshold, to_hard_lh
from app.arrangement.theory import ROOT_VELOCITY, INNER_VOICE_VELOCITY
```

with:

```python
from app.arrangement.hard import to_hard_lh
from app.arrangement.theory import ROOT_VELOCITY, INNER_VOICE_VELOCITY, short_chord_threshold
```

And replace both call sites of `_short_chord_threshold(...)` in that file (in `test_short_chord_threshold_is_one_and_a_half_bars_at_the_given_tempo` and `test_short_chord_threshold_scales_with_tempo`) with `short_chord_threshold(...)`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrangement_hard.py -v`
Expected: FAIL — `ImportError: cannot import name '_short_chord_threshold' from 'app.arrangement.hard'` (it still exists there until Step 3, so this actually will currently PASS on the old function; the point of this step is the import of `short_chord_threshold` from `theory` — confirm that succeeds, and that `_short_chord_threshold` is genuinely gone from `hard.py`'s public surface only after Step 3). Run it once now to confirm current state (should still pass, since `hard.py` hasn't changed yet), then re-run after Step 3 to confirm the refactor didn't break anything.

- [ ] **Step 3: Refactor hard.py**

Replace the full contents of `backend/app/arrangement/hard.py` with:

```python
from music21 import clef, note, stream

from app.arrangement.theory import (
    ROOT_VELOCITY,
    INNER_VOICE_VELOCITY,
    lh_voicing,
    pitch_class_to_midi_in_range,
    quantized_duration,
    round_to_grid,
    stack_above,
)
from app.arrangement.types import ChordSymbol
from app.notation.hand_split import SECONDS_PER_QUARTER

HARD_LH_RANGE = (36, 55)  # C2-G3, same bass register as the Medium tier
ARPEGGIO_STEP = 0.5  # eighth note, in quarterLength units
# Classic Alberti-bass order: root, fifth, third, fifth (indices into
# lh_voicing()'s root-first tone ordering). The inner `% len(tones)`
# handles chords with fewer tones than the pattern references.
ALBERTI_INDICES = (0, 2, 1, 2)
# On a long-held chord, repeating the same 4-note Alberti cycle unchanged
# reads as "the same chord playing over and over" — every Nth cycle lifts
# an octave for variety. Short/normal-length chords rarely reach a second
# cycle at all, so this only kicks in on genuinely long holds.
CYCLES_BETWEEN_OCTAVE_LIFTS = 4


def to_hard_lh(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """A full block chord for short chords, an Alberti-bass arpeggio
    (root-fifth-third-fifth, subdivided into eighth notes) for longer
    ones — variety instead of one repeating pattern regardless of
    context."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    step_seconds = ARPEGGIO_STEP * seconds_per_quarter

    for chord in chords:
        tones, is_short = lh_voicing(chord, seconds_per_quarter)
        root_midi = pitch_class_to_midi_in_range(tones[0], *HARD_LH_RANGE)

        if is_short:
            offset = round_to_grid(chord.start / seconds_per_quarter)
            length = quantized_duration(chord.duration, seconds_per_quarter)
            for pitch_class in tones:
                n = note.Note()
                n.pitch.midi = stack_above(root_midi, pitch_class)
                n.duration.quarterLength = length
                n.volume.velocityScalar = ROOT_VELOCITY if pitch_class == tones[0] else INNER_VOICE_VELOCITY
                part.insert(offset, n)
            continue

        step = 0
        elapsed = 0.0
        while elapsed < chord.duration:
            cycle = step // len(ALBERTI_INDICES)
            index = ALBERTI_INDICES[step % len(ALBERTI_INDICES)] % len(tones)
            pitch_class = tones[index]
            offset = round_to_grid((chord.start + elapsed) / seconds_per_quarter)
            octave_lift = 12 if cycle % CYCLES_BETWEEN_OCTAVE_LIFTS == CYCLES_BETWEEN_OCTAVE_LIFTS - 1 else 0

            n = note.Note()
            n.pitch.midi = stack_above(root_midi, pitch_class) + octave_lift
            n.duration.quarterLength = ARPEGGIO_STEP
            n.volume.velocityScalar = ROOT_VELOCITY if index == 0 else INNER_VOICE_VELOCITY
            part.insert(offset, n)

            step += 1
            elapsed += step_seconds

    return part
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrangement_hard.py tests/test_arrangement_theory.py -v`
Expected: PASS (all tests, unchanged assertions).

- [ ] **Step 5: Commit**

```bash
git add backend/app/arrangement/hard.py backend/tests/test_arrangement_hard.py
git commit -m "refactor: hard.py reads tones from the shared lh_voicing()"
```

---

### Task 3: Refactor `easy.py` and `medium.py` to use `lh_voicing`, add the consolidation contract test

**Files:**
- Modify: `backend/app/arrangement/easy.py`
- Modify: `backend/app/arrangement/medium.py`
- Create: `backend/tests/test_arrangement_consolidation.py`

**Interfaces:**
- Consumes: `lh_voicing` from `app.arrangement.theory` (Task 1); `to_easy_lh`, `to_medium_lh`, `to_hard_lh` (unchanged signatures); `MAX_BLOCK_TONES` from `medium.py` (unchanged).
- Produces: nothing new consumed by later tasks — this is the last task.

- [ ] **Step 1: Write the failing consolidation contract test**

Create `backend/tests/test_arrangement_consolidation.py`:

```python
from app.arrangement.easy import to_easy_lh
from app.arrangement.hard import to_hard_lh
from app.arrangement.medium import MAX_BLOCK_TONES, to_medium_lh
from app.arrangement.theory import lh_voicing
from app.arrangement.types import ChordSymbol


def test_easy_note_is_lh_voicings_first_tone():
    # Consolidation contract: Easy's single note must be a literal read of
    # lh_voicing()'s tones, not an independently chosen pitch class — this
    # is what keeps the three tiers from silently re-diverging over time.
    chord = ChordSymbol(start=0.0, duration=1.0, root=0, quality="dom7")
    tones, _ = lh_voicing(chord, seconds_per_quarter=0.5)

    part = to_easy_lh([chord])
    played = {n.pitch.pitchClass for n in part.flatten().notes}
    assert played == {tones[0]}


def test_medium_block_chord_is_a_prefix_of_lh_voicings_tones():
    chord = ChordSymbol(start=0.0, duration=1.0, root=0, quality="dom7")
    tones, _ = lh_voicing(chord, seconds_per_quarter=0.5)

    part = to_medium_lh([chord])
    played = {n.pitch.pitchClass for n in part.flatten().notes}
    assert played == set(tones[:MAX_BLOCK_TONES])


def test_hard_uses_the_full_lh_voicing_tone_set_on_a_short_chord():
    chord = ChordSymbol(start=0.0, duration=0.5, root=0, quality="dom7")
    tones, is_short = lh_voicing(chord, seconds_per_quarter=0.5)
    assert is_short is True

    part = to_hard_lh([chord])
    played = {n.pitch.pitchClass for n in part.flatten().notes}
    assert played == set(tones)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrangement_consolidation.py -v`
Expected: PASS for `test_hard_uses_the_full_lh_voicing_tone_set_on_a_short_chord` (Task 2 already made Hard consistent) but FAIL for the two Easy/Medium tests — `AssertionError`, since `easy.py`/`medium.py` still call `chord_tones(...)` independently rather than `lh_voicing(...)` (the assertion itself will likely still numerically pass today since the tone sets happen to match; if so, note in the commit message that this step is establishing the *contract*, not fixing a numeric bug — proceed to Step 3 regardless so the dependency is explicit, not coincidental).

- [ ] **Step 3: Refactor easy.py**

Replace the full contents of `backend/app/arrangement/easy.py` with:

```python
from music21 import clef, note, stream

from app.arrangement.theory import ROOT_VELOCITY, lh_voicing, pitch_class_to_midi_in_range, quantized_duration, round_to_grid
from app.arrangement.types import ChordSymbol
from app.notation.hand_split import SECONDS_PER_QUARTER

EASY_LH_RANGE = (36, 48)  # C2-C3, matches difficulty/easy.py's LH range


def to_easy_lh(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """One root note per chord, held for the chord's full duration."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    for chord in chords:
        tones, _ = lh_voicing(chord, seconds_per_quarter)
        offset = round_to_grid(chord.start / seconds_per_quarter)
        length = quantized_duration(chord.duration, seconds_per_quarter)
        midi = pitch_class_to_midi_in_range(tones[0], *EASY_LH_RANGE)
        n = note.Note()
        n.pitch.midi = midi
        n.duration.quarterLength = length
        n.volume.velocityScalar = ROOT_VELOCITY
        part.insert(offset, n)
    return part
```

- [ ] **Step 4: Refactor medium.py**

Replace the full contents of `backend/app/arrangement/medium.py` with:

```python
from music21 import clef, note, stream

from app.arrangement.theory import (
    ROOT_VELOCITY,
    INNER_VOICE_VELOCITY,
    lh_voicing,
    pitch_class_to_midi_in_range,
    quantized_duration,
    round_to_grid,
    stack_above,
)
from app.arrangement.types import ChordSymbol
from app.notation.hand_split import SECONDS_PER_QUARTER

MEDIUM_LH_RANGE = (36, 55)  # C2-G3, matches difficulty/medium.py's LH range
MAX_BLOCK_TONES = 3  # root + third + fifth; drop the 7th for playability


def to_medium_lh(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """A close-position block chord (root + third + fifth) per chord,
    held for the chord's full duration."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    for chord in chords:
        all_tones, _ = lh_voicing(chord, seconds_per_quarter)
        tones = all_tones[:MAX_BLOCK_TONES]
        offset = round_to_grid(chord.start / seconds_per_quarter)
        length = quantized_duration(chord.duration, seconds_per_quarter)
        root_midi = pitch_class_to_midi_in_range(tones[0], *MEDIUM_LH_RANGE)
        for pitch_class in tones:
            n = note.Note()
            n.pitch.midi = stack_above(root_midi, pitch_class)
            n.duration.quarterLength = length
            n.volume.velocityScalar = ROOT_VELOCITY if pitch_class == tones[0] else INNER_VOICE_VELOCITY
            part.insert(offset, n)
    return part
```

- [ ] **Step 5: Run the full arrangement test suite to verify everything passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrangement_easy.py tests/test_arrangement_medium.py tests/test_arrangement_hard.py tests/test_arrangement_engine.py tests/test_arrangement_theory.py tests/test_arrangement_consolidation.py tests/test_arrangement_notation_grid.py -v`
Expected: PASS — every test, including all pre-existing ones with unmodified assertions.

- [ ] **Step 6: Run the full backend test suite as a regression check**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS. If anything outside the arrangement module fails, stop and investigate before committing — it means this refactor had an unintended side effect (it shouldn't; `easy.py`/`medium.py`/`hard.py`/`theory.py` have no other callers besides `engine.py` and `arrange_pipeline.py`, both of which only use the unchanged `to_easy_lh`/`to_medium_lh`/`to_hard_lh` signatures).

- [ ] **Step 7: Commit**

```bash
git add backend/app/arrangement/easy.py backend/app/arrangement/medium.py backend/tests/test_arrangement_consolidation.py
git commit -m "refactor: easy.py and medium.py read tones from the shared lh_voicing()

Closes the LH consolidation gap: all three difficulty tiers now derive
their chord tones from one function (theory.lh_voicing) instead of each
independently calling chord_tones(), with a contract test locking this in
so the tiers can't silently re-diverge again."
```

---

## Deferred (not in scope for this plan)

Making the *rhythmic* content of Easy/Medium (currently static held blocks) an actual reduction of Hard's rendered note stream — analogous to RH's `quantize_part` — was considered and rejected for this plan: Hard's output alternates between simultaneous block chords (short chords) and sequential single-note arpeggios (long chords), which isn't the same shape as RH's monophonic stream, and reconstructing tier-appropriate voicings by reverse-engineering rendered notes (offsets, velocities) is fragile compared to sharing the tone-selection step directly (what this plan does). If a future session wants Easy/Medium to also inherit rhythmic simplification from Hard, that needs its own design pass.

Making the single rich LH tier musically richer than the current Alberti-bass pattern (voice-leading between chords, walking bass, syncopation, per the "songscription.ai" reference in `docs/superpowers/plans/2026-09-01-arrangement-engine.md`'s follow-up notes) is explicitly out of scope here — it's a creative/musical decision that needs by-ear iteration against real songs, not something to delegate to an unsupervised agent.
