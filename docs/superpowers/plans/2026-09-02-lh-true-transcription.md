# LH True Transcription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace chord-symbol-driven LH synthesis with a real transcription of the song's harmony (bass+other stem mix), mirroring how RH already works: one rich Hard-tier transcription, with Easy/Medium mechanically derived from it via a generalized `quantize_part(max_voices=N)` + the existing `shift_into_range`.

**Architecture:** New `app/lh/extract.py` runs Basic Pitch on the harmony audio and caps over-detected polyphony to a plausible voice count, producing the Hard-tier LH base — the LH analogue of `app/melody/extract.py`. `app/difficulty/quantize.py::quantize_part` gains an optional `max_voices` parameter (default `1`, preserving RH's exact current behavior) so the same function derives both hands' Easy/Medium tiers. `app/chords/detect.py` is trimmed to key+tempo detection only (`detect_key_and_tempo`) — chord-symbol matching is no longer needed by anything. The entire `app/arrangement/` package and `app/chords/match.py`/`templates.py` are retired.

**Tech Stack:** Python, music21, Basic Pitch (already a dependency, already used for RH), pytest — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-02-lh-true-transcription-design.md` — read this first; this plan implements it task-by-task without repeating its rationale.

## Global Constraints

- RH behavior must not change at all: `quantize_part`'s default (`max_voices=1`) must produce byte-identical output to today, verified by running the full existing RH-facing test suite unmodified.
- No dependency on anything in `app/arrangement/` or `app/chords/match.py`/`templates.py` may survive past Task 4 — they're fully deleted, not deprecated/kept-for-compat.
- Follow this repo's TDD discipline: write the failing test, verify the exact failure, implement, verify green, commit — for every step below.
- Tasks 1-3 touch disjoint files and have no dependency on each other — they can be implemented in parallel. Task 4 depends on all three being complete (it imports the real names Tasks 1-3 produce) and must run after them.

---

### Task 1: `app/lh/extract.py` — LH transcription with polyphony capping

**Files:**
- Create: `backend/app/lh/__init__.py` (empty)
- Create: `backend/app/lh/extract.py`
- Test: `backend/tests/test_lh_extract.py`

**Interfaces:**
- Consumes: `NoteEvent` (`app.notation.types`), `transcribe_audio_to_notes` (`app.transcription.audio_to_midi`), `notes_to_part`/`SECONDS_PER_QUARTER` (`app.notation.hand_split`), `shift_into_range` (`app.difficulty.range_shift`) — all pre-existing, unchanged.
- Produces (for Task 4): `extract_lh_notes(audio_path: str, max_voices: int = HARD_MAX_VOICES) -> list[NoteEvent]`, `build_lh_part(notes: list[NoteEvent], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part`, plus `cap_simultaneous_notes(notes: list[NoteEvent], max_voices: int) -> list[NoteEvent]` and constants `HARD_MAX_VOICES = 4`, `HARD_LH_RANGE = (36, 55)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/app/lh/__init__.py` (empty file).

Create `backend/tests/test_lh_extract.py`:

```python
from app.lh.extract import HARD_LH_RANGE, build_lh_part, cap_simultaneous_notes, extract_lh_notes
from app.notation.types import NoteEvent


def test_cap_simultaneous_notes_passes_through_when_under_the_cap():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=48, velocity=0.6),
        NoteEvent(start=0.0, end=1.0, pitch=52, velocity=0.7),
    ]
    assert cap_simultaneous_notes(notes, max_voices=3) == notes


def test_cap_simultaneous_notes_drops_the_weakest_note_over_the_cap():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=48, velocity=0.9),
        NoteEvent(start=0.0, end=1.0, pitch=52, velocity=0.5),
        NoteEvent(start=0.0, end=1.0, pitch=55, velocity=0.7),
        NoteEvent(start=0.0, end=1.0, pitch=59, velocity=0.2),  # weakest — dropped
    ]
    result = cap_simultaneous_notes(notes, max_voices=3)
    assert len(result) == 3
    assert notes[3] not in result


def test_cap_simultaneous_notes_evicts_a_held_note_when_a_stronger_one_arrives_later():
    notes = [
        NoteEvent(start=0.0, end=2.0, pitch=48, velocity=0.3),  # weak, held from t=0
        NoteEvent(start=0.0, end=2.0, pitch=52, velocity=0.6),
        NoteEvent(start=1.0, end=2.0, pitch=55, velocity=0.9),  # arrives later, stronger than the weak held note
    ]
    result = cap_simultaneous_notes(notes, max_voices=2)
    assert notes[0] not in result  # evicted — still sounding at t=1.0 but weakest
    assert notes[1] in result
    assert notes[2] in result


def test_cap_simultaneous_notes_favors_the_earlier_note_on_a_confidence_tie():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=48, velocity=0.5),
        NoteEvent(start=0.0, end=1.0, pitch=52, velocity=0.5),
        NoteEvent(start=0.2, end=0.8, pitch=55, velocity=0.5),  # same confidence, arrives later
    ]
    result = cap_simultaneous_notes(notes, max_voices=2)
    assert result == [notes[0], notes[1]]


def test_cap_simultaneous_notes_frees_a_voice_once_a_held_note_ends():
    notes = [
        NoteEvent(start=0.0, end=0.5, pitch=48, velocity=0.9),
        NoteEvent(start=0.0, end=0.5, pitch=52, velocity=0.8),
        NoteEvent(start=0.6, end=1.0, pitch=55, velocity=0.1),  # starts after both earlier notes ended
    ]
    result = cap_simultaneous_notes(notes, max_voices=2)
    assert result == notes  # no eviction needed — the first two had already ended


def test_extract_lh_notes_caps_to_max_voices(monkeypatch):
    import app.lh.extract as lh_extract_module

    fake_notes = [
        NoteEvent(start=0.0, end=1.0, pitch=48, velocity=0.9),
        NoteEvent(start=0.0, end=1.0, pitch=52, velocity=0.8),
        NoteEvent(start=0.0, end=1.0, pitch=55, velocity=0.1),
    ]
    monkeypatch.setattr(lh_extract_module, "transcribe_audio_to_notes", lambda audio_path: fake_notes)

    notes = extract_lh_notes("fake/path.wav", max_voices=2)
    assert len(notes) == 2


def test_extract_lh_notes_detects_content_near_a4(synthetic_piano_wav):
    notes = extract_lh_notes(str(synthetic_piano_wav))
    assert len(notes) >= 1
    pitches = [n.pitch for n in notes]
    assert any(abs(p - 69) <= 2 for p in pitches)  # A4 = MIDI 69, same synthetic tone as melody's fixture


def test_build_lh_part_shifts_notes_into_the_hard_range():
    notes = [NoteEvent(start=0.0, end=1.0, pitch=84)]  # C6, above HARD_LH_RANGE
    part = build_lh_part(notes)
    pitches = [n.pitch.midi for n in part.flatten().notes]
    assert all(HARD_LH_RANGE[0] <= p <= HARD_LH_RANGE[1] for p in pitches)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_lh_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.lh'`.

- [ ] **Step 3: Implement `app/lh/extract.py`**

```python
from music21 import stream

from app.difficulty.range_shift import shift_into_range
from app.notation.hand_split import SECONDS_PER_QUARTER, notes_to_part
from app.notation.types import NoteEvent
from app.transcription.audio_to_midi import transcribe_audio_to_notes

HARD_MAX_VOICES = 4  # a plausible upper bound on notes one hand plays at once
HARD_LH_RANGE = (36, 55)  # C2-G3, same bass register as the previous Hard tier


def cap_simultaneous_notes(notes: list[NoteEvent], max_voices: int) -> list[NoteEvent]:
    """At every moment, keep at most max_voices concurrently-sounding
    notes — the highest-velocity ones — discarding the rest. Basic Pitch
    on a busy 'other' stem (piano/guitar/strings/synths — whatever Demucs
    didn't call vocals/drums/bass) can over-detect beyond what a hand can
    physically play; this caps to a plausible upper bound rather than
    trusting raw detection count, generalizing melody.extract's
    reduce_to_monophonic (confidence-over-raw-detection) from 1 voice to
    N. On a tie, the earlier-processed (already-held) note wins."""
    ordered = sorted(notes, key=lambda n: n.start)
    held: list[NoteEvent] = []
    kept: list[NoteEvent] = []
    for candidate in ordered:
        held = [n for n in held if n.end > candidate.start]
        if len(held) < max_voices:
            held.append(candidate)
            kept.append(candidate)
            continue
        weakest = min(held, key=lambda n: n.velocity)
        if candidate.velocity <= weakest.velocity:
            continue
        held.remove(weakest)
        kept.remove(weakest)
        held.append(candidate)
        kept.append(candidate)
    return kept


def extract_lh_notes(audio_path: str, max_voices: int = HARD_MAX_VOICES) -> list[NoteEvent]:
    """Run Basic Pitch on harmony audio (bass+other mix) and cap to
    max_voices concurrently-sounding notes. Unlike RH, deliberately keeps
    polyphony — real LH accompaniment is chordal, not a single line."""
    notes = transcribe_audio_to_notes(audio_path)
    return cap_simultaneous_notes(notes, max_voices)


def build_lh_part(notes: list[NoteEvent], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """Register-shift the capped transcription into HARD_LH_RANGE and
    build the LH 'Hard' Part — the full-detail base every difficulty tier
    derives from, same role as melody.extract.build_melody_part for RH."""
    part = notes_to_part(notes, part_id="LH", seconds_per_quarter=seconds_per_quarter)
    return shift_into_range(part, *HARD_LH_RANGE)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_lh_extract.py -v`
Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/lh/__init__.py backend/app/lh/extract.py backend/tests/test_lh_extract.py
git commit -m "feat: add app/lh/extract.py — real LH transcription with polyphony capping"
```

---

### Task 2: Generalize `quantize_part` to support polyphonic voice-capping

**Files:**
- Modify: `backend/app/difficulty/quantize.py`
- Modify: `backend/tests/test_quantize.py`

**Interfaces:**
- Consumes: nothing new (already imports `carry_clef` from `app.notation.hand_split`).
- Produces (for Task 4): `quantize_part(part: stream.Part, grid: float, max_voices: int = 1) -> stream.Part` — `max_voices=1` (the default, and RH's only call site) is byte-identical to today's behavior; `max_voices > 1` keeps the top-N-by-velocity notes per grid slot, deduped by pitch class.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_quantize.py`:

```python
def test_max_voices_default_still_keeps_first_note_per_slot():
    # Regression: explicit max_voices=1 must match the pre-existing default.
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("C4"))
    part.insert(0.1, note.Note("D4"))
    quantized = quantize_part(part, grid=1.0, max_voices=1)
    pitches = [n.pitch.name for n in quantized.flatten().notes]
    assert pitches == ["C"]


def test_max_voices_caps_notes_per_slot_by_velocity():
    part = stream.Part(id="LH")
    for pitch_name, velocity in [("C3", 0.9), ("E3", 0.5), ("G3", 0.7), ("B3", 0.3)]:
        n = note.Note(pitch_name)
        n.volume.velocityScalar = velocity
        part.insert(0.0, n)

    quantized = quantize_part(part, grid=1.0, max_voices=3)

    pitches = sorted(n.pitch.name for n in quantized.flatten().notes)
    assert pitches == ["C", "E", "G"]  # B3 (lowest velocity) dropped


def test_max_voices_dedups_repeated_pitch_class_keeping_higher_velocity():
    part = stream.Part(id="LH")
    n1 = note.Note("C3")
    n1.volume.velocityScalar = 0.4
    n2 = note.Note("C4")
    n2.volume.velocityScalar = 0.9
    part.insert(0.0, n1)
    part.insert(0.0, n2)

    quantized = quantize_part(part, grid=1.0, max_voices=3)

    notes = list(quantized.flatten().notes)
    assert len(notes) == 1
    assert notes[0].pitch.midi == 60  # C4 (higher-velocity instance) kept, not C3


def test_max_voices_preserves_clef():
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    n = note.Note("C3")
    n.volume.velocityScalar = 0.5
    part.insert(0.0, n)

    quantized = quantize_part(part, grid=1.0, max_voices=3)

    clefs = quantized.getElementsByClass(clef.Clef)
    assert len(clefs) == 1
    assert isinstance(clefs[0], clef.BassClef)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_quantize.py -v`
Expected: `test_max_voices_default_still_keeps_first_note_per_slot` PASSES already (current signature ignores the extra kwarg? No — it will FAIL with `TypeError: quantize_part() got an unexpected keyword argument 'max_voices'`, since `max_voices` doesn't exist yet). All four new tests FAIL with that TypeError.

- [ ] **Step 3: Implement**

Replace the full contents of `backend/app/difficulty/quantize.py` with:

```python
import copy

from music21 import stream

from app.notation.hand_split import carry_clef


def quantize_part(part: stream.Part, grid: float, max_voices: int = 1) -> stream.Part:
    """Snap note onsets to the given grid (in quarterLength units),
    keeping at most max_voices notes per slot. At max_voices=1 (the
    default, and RH's only call site), keeps whichever note was
    encountered first per slot, exactly as before. Above 1, keeps the
    highest-velocity notes among all notes whose onset falls in the slot
    (deduping repeated pitch classes to their higher-velocity instance
    first) — used for LH's polyphonic Easy/Medium reduction, where
    "first encountered" isn't a meaningful tie-break the way it is for a
    single melody line."""
    by_slot: dict[float, list] = {}
    for element in part.flatten().notes:
        slot = (element.offset // grid) * grid
        by_slot.setdefault(slot, []).append(element)

    quantized = stream.Part(id=part.id)
    for slot in sorted(by_slot):
        candidates = by_slot[slot]
        kept = [candidates[0]] if max_voices == 1 else _cap_voices(candidates, max_voices)
        for element in kept:
            new_element = copy.deepcopy(element)
            new_element.duration.quarterLength = grid
            quantized.insert(slot, new_element)

    carry_clef(part, quantized)
    return quantized


def _cap_voices(candidates: list, max_voices: int) -> list:
    """Dedup by pitch class (keeping the higher-velocity instance of
    each), then cap at max_voices, highest-velocity first."""
    by_pitch_class: dict[int, object] = {}
    for element in candidates:
        pitch_class = element.pitch.pitchClass
        existing = by_pitch_class.get(pitch_class)
        if existing is None or element.volume.velocityScalar > existing.volume.velocityScalar:
            by_pitch_class[pitch_class] = element
    ordered = sorted(by_pitch_class.values(), key=lambda n: n.volume.velocityScalar, reverse=True)
    return ordered[:max_voices]
```

- [ ] **Step 4: Run the full quantize test suite to verify everything passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_quantize.py -v`
Expected: PASS — all pre-existing tests (unmodified) plus the 4 new ones.

- [ ] **Step 5: Run the full backend suite as an RH regression check**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS. Nothing outside `test_quantize.py` should be affected — `quantize_part`'s only other callers (`app/difficulty/easy.py`/`medium.py`/`arrange_pipeline.py`) call it without `max_voices`, so they get the unchanged default.

- [ ] **Step 6: Commit**

```bash
git add backend/app/difficulty/quantize.py backend/tests/test_quantize.py
git commit -m "feat: quantize_part gains max_voices for polyphonic LH reduction"
```

---

### Task 3: Trim chord detection to key+tempo only

**Files:**
- Modify: `backend/app/chords/detect.py`
- Modify: `backend/app/chords/key.py`
- Delete: `backend/app/chords/match.py`
- Delete: `backend/app/chords/templates.py`
- Modify: `backend/tests/test_chords_detect.py`
- Modify: `backend/tests/test_chords_key.py`
- Delete: `backend/tests/test_chords_match.py`

**Interfaces:**
- Consumes: `detect_key` (`app.chords.key`, unchanged), `librosa`, `numpy` (unchanged).
- Produces (for Task 4): `detect_key_and_tempo(audio_path: str) -> tuple[tuple[int, str], float]` — returns `(key, seconds_per_quarter)`.

- [ ] **Step 1: Update the test files (this is the "failing test" step for a trim/refactor)**

Replace the full contents of `backend/tests/test_chords_detect.py` with:

```python
import pytest

from app.chords.detect import _tempo_to_seconds_per_quarter, detect_key_and_tempo


def test_tempo_to_seconds_per_quarter_converts_bpm():
    assert _tempo_to_seconds_per_quarter(120.0) == 0.5
    assert _tempo_to_seconds_per_quarter(60.0) == 1.0


def test_tempo_to_seconds_per_quarter_clamps_extreme_values():
    assert _tempo_to_seconds_per_quarter(20.0) == 60.0 / 60.0   # clamped up to MIN_TEMPO_BPM
    assert _tempo_to_seconds_per_quarter(500.0) == 60.0 / 200.0  # clamped down to MAX_TEMPO_BPM


def test_tempo_to_seconds_per_quarter_falls_back_on_zero_or_none():
    assert _tempo_to_seconds_per_quarter(0.0) == 0.5
    assert _tempo_to_seconds_per_quarter(None) == 0.5


def test_detect_key_and_tempo_returns_a_key_and_positive_tempo(synthetic_piano_wav):
    key, seconds_per_quarter = detect_key_and_tempo(str(synthetic_piano_wav))
    tonic, mode = key
    assert 0 <= tonic <= 11
    assert mode in ("major", "minor")
    assert seconds_per_quarter > 0
```

(This deletes every test tied to bar-chord matching/absorption — `_absorb_short_chords`, `_merge_consecutive`, `_min_chord_duration`, the old `detect_chords` — since that machinery no longer exists after this task.)

Replace the full contents of `backend/tests/test_chords_key.py` with:

```python
import numpy as np

from app.chords.key import MAJOR_PROFILE, MINOR_PROFILE, detect_key


def test_detect_key_recovers_a_rotated_major_profile():
    rotated = np.roll(MAJOR_PROFILE, 4)  # simulate a song centered on E major (tonic=4)
    chroma = rotated.reshape(12, 1)
    assert detect_key(chroma) == (4, "major")


def test_detect_key_recovers_a_rotated_minor_profile():
    rotated = np.roll(MINOR_PROFILE, 9)  # simulate a song centered on A minor (tonic=9)
    chroma = rotated.reshape(12, 1)
    assert detect_key(chroma) == (9, "minor")
```

(This drops every `is_diatonic`-related test and the `is_diatonic` import — that function is being removed from `app/chords/key.py` in Step 3, since its only caller, `match.py`, no longer exists.)

Delete `backend/tests/test_chords_match.py` entirely (`rm backend/tests/test_chords_match.py`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_detect.py tests/test_chords_key.py -v`
Expected: FAIL — `ImportError: cannot import name 'detect_key_and_tempo' from 'app.chords.detect'` (it doesn't exist yet) and an `ImportError` on `is_diatonic` still being imported by `key.py`'s own module-level `from app.chords.templates import BASE_TRIAD` should still succeed at this point (templates.py isn't deleted yet) — the actual failure here is purely the missing `detect_key_and_tempo` name.

- [ ] **Step 3: Implement `app/chords/detect.py`**

Replace the full contents of `backend/app/chords/detect.py` with:

```python
import librosa
import numpy as np

from app.chords.key import detect_key

MIN_TEMPO_BPM = 60.0
MAX_TEMPO_BPM = 200.0
DEFAULT_SECONDS_PER_QUARTER = 0.5  # 120 BPM fallback if beat-tracking yields nothing usable


def _tempo_to_seconds_per_quarter(tempo) -> float:
    """Convert a detected tempo (BPM, possibly a numpy scalar/array, or
    falsy) to seconds-per-quarter-note, clamped to a musically sane range
    — beat tracking on noisy or atypical audio occasionally returns
    implausible outliers (near-zero, or half/double-tempo errors)."""
    bpm = float(np.atleast_1d(tempo)[0]) if tempo else 0.0
    if bpm <= 0:
        return DEFAULT_SECONDS_PER_QUARTER
    bpm = min(max(bpm, MIN_TEMPO_BPM), MAX_TEMPO_BPM)
    return 60.0 / bpm


def detect_key_and_tempo(audio_path: str) -> tuple[tuple[int, str], float]:
    """Detect the song's key (tonic pitch class, mode) and tempo (as
    seconds-per-quarter-note) from an audio file. Chroma-based key
    detection and beat-tracking only — no chord-per-bar matching; LH now
    comes from a real transcription (app.lh.extract) rather than chord
    symbols, so this only needs to supply the key signature and the
    tempo used to convert note timings."""
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    key = detect_key(chroma)
    tempo, _beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    seconds_per_quarter = _tempo_to_seconds_per_quarter(tempo)
    return key, seconds_per_quarter
```

Delete `backend/app/chords/match.py` and `backend/app/chords/templates.py` entirely (`rm` both).

Replace the full contents of `backend/app/chords/key.py` with:

```python
import numpy as np

# Krumhansl-Kessler key profiles — standard, published empirical
# constants from music cognition research (relative perceived
# "fit" of each pitch class to a major/minor tonal center), used
# here via correlation against a song's overall chroma distribution
# to estimate its key.
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def detect_key(chroma: np.ndarray) -> tuple[int, str]:
    """Estimate a song's key (tonic pitch class, mode) from its overall
    chroma distribution via Krumhansl-Schmuckler key-profile
    correlation: try every (tonic, mode) combination and pick whichever
    rotated profile correlates best with the song's actual pitch-class
    usage."""
    overall = chroma.mean(axis=1)
    best_score = -np.inf
    best_key = (0, "major")
    for tonic in range(12):
        for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            rotated = np.roll(profile, tonic)
            score = float(np.corrcoef(overall, rotated)[0, 1])
            if score > best_score:
                best_score = score
                best_key = (tonic, mode)
    return best_key
```

This drops `is_diatonic`, its `from app.chords.templates import BASE_TRIAD` import, and `MAJOR_DIATONIC_QUALITIES`/`MINOR_DIATONIC_QUALITIES` (all now unused — `is_diatonic` was only called by `match.py`, which no longer exists, and those two dicts were only used by `is_diatonic`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_detect.py tests/test_chords_key.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite as a regression check**

Run: `cd backend && ./.venv/bin/python -m pytest -v --ignore=tests/test_api.py`
(`test_api.py` still references the now-deleted `app.arrangement.types.ChordSymbol` and mocks the now-deleted `detect_chords` — that's Task 4's job to fix, so it's expected to fail/error at collection time until Task 4 lands. Everything else should pass.)
Expected: PASS for every collected test outside `test_api.py`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/chords/detect.py backend/app/chords/key.py backend/tests/test_chords_detect.py backend/tests/test_chords_key.py
git rm backend/app/chords/match.py backend/app/chords/templates.py backend/tests/test_chords_match.py
git commit -m "refactor: trim chord detection to key+tempo, drop chord-symbol matching"
```

---

### Task 4: Wire up `_lh_variants`, retire `app/arrangement/`, verify end-to-end

**Depends on:** Tasks 1, 2, 3 complete and merged — this task imports `app.lh.extract.extract_lh_notes`/`build_lh_part`, `app.difficulty.quantize.quantize_part`'s `max_voices` param, and `app.chords.detect.detect_key_and_tempo`, all as delivered by those tasks (not as drafted in this plan — if any of Tasks 1-3 deviated from their plan text during implementation, use their actual final signatures).

**Files:**
- Modify: `backend/app/arrange_pipeline.py`
- Modify: `backend/tests/test_api.py`
- Modify: `frontend/src/api/arrange.ts`
- Delete: `backend/app/arrangement/` (entire package: `__init__.py`, `easy.py`, `medium.py`, `hard.py`, `engine.py`, `theory.py`, `types.py`)
- Delete: `backend/tests/test_arrangement_easy.py`, `test_arrangement_engine.py`, `test_arrangement_hard.py`, `test_arrangement_medium.py`, `test_arrangement_notation_grid.py`, `test_arrangement_theory.py`, `test_arrangement_consolidation.py`

- [ ] **Step 1: Update `backend/tests/test_api.py` (failing-test step)**

In `backend/tests/test_api.py`, find the `test_arrange_full_job_lifecycle_returns_transcribe_shaped_result` test (around line 266) and its `from app.arrangement.types import ChordSymbol` import (around line 261). Replace that import line and the test's mocking of `detect_chords` with:

```python
from app.notation.types import NoteEvent
from app.separation.types import Stems


def test_arrange_full_job_lifecycle_returns_transcribe_shaped_result(monkeypatch, synthetic_piano_wav):
    import app.arrange_pipeline as pipeline_module

    fake_notes = [NoteEvent(start=0.0, end=0.5, pitch=72)]
    fake_lh_notes = [NoteEvent(start=0.0, end=0.5, pitch=48)]

    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=Path("/fake/vocals.wav"), drums=Path("/fake/drums.wav"),
            bass=Path("/fake/bass.wav"), other=Path("/fake/other.wav"),
        ),
    )
    monkeypatch.setattr(pipeline_module, "mix_wav_files", lambda a, b, dest: dest)
    monkeypatch.setattr(pipeline_module, "extract_melody_notes", lambda audio_path: fake_notes)
    monkeypatch.setattr(pipeline_module, "extract_lh_notes", lambda audio_path: fake_lh_notes)
    monkeypatch.setattr(
        pipeline_module, "detect_key_and_tempo",
        lambda audio_path: ((0, "major"), 0.5),
    )
```

(Leave the rest of that test function — from `with open(synthetic_piano_wav, "rb") as f:` onward — unchanged; it doesn't reference chords.)

- [ ] **Step 2: Run test_api.py to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -v`
Expected: FAIL — collection error (`ModuleNotFoundError: No module named 'app.arrangement'` no longer true yet since we haven't deleted it, but `pipeline_module` doesn't yet have `extract_lh_notes`/`detect_key_and_tempo` attributes, so `monkeypatch.setattr` raises `AttributeError: <module 'app.arrange_pipeline'> does not have the attribute 'extract_lh_notes'`).

- [ ] **Step 3: Rewrite `backend/app/arrange_pipeline.py`**

Replace the full contents of `backend/app/arrange_pipeline.py` with:

```python
import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.io import wavfile

from app.chords.detect import detect_key_and_tempo
from app.difficulty.easy import EASY_GRID, EASY_LH_RANGE, EASY_RH_RANGE
from app.difficulty.medium import MEDIUM_GRID, MEDIUM_LH_RANGE, MEDIUM_RH_RANGE
from app.difficulty.quantize import quantize_part
from app.difficulty.range_shift import shift_into_range
from app.export import export_musicxml
from app.jobs import set_failed, set_result, set_status
from app.lh.extract import build_lh_part, extract_lh_notes
from app.melody.extract import build_melody_part, extract_melody_notes
from app.notation.hand_split import SECONDS_PER_QUARTER, build_grand_staff_score, key_signature_from_tonic
from app.separation.separator import separate_stems
from app.storage import evict_oldest_songs, write_metadata

MEDIUM_LH_MAX_VOICES = 3  # matches the previous arrangement/medium.py's MAX_BLOCK_TONES


def _rh_variants(melody_notes, seconds_per_quarter: float = SECONDS_PER_QUARTER):
    """Build the three difficulty tiers' RH Parts from one cleaned melody
    base — Easy/Medium reuse Spec 1's own quantize_part (thins note
    density to the grid) and shift_into_range (narrows register) so the
    right hand actually gets harder as the tier increases; Hard keeps the
    full-detail base unchanged, same "no further simplification"
    philosophy as Spec 1's Hard tier."""
    base = build_melody_part(melody_notes, seconds_per_quarter)
    return {
        "easy": shift_into_range(quantize_part(base, EASY_GRID), *EASY_RH_RANGE),
        "medium": shift_into_range(quantize_part(base, MEDIUM_GRID), *MEDIUM_RH_RANGE),
        "hard": base,
    }


def _lh_variants(harmony_path: str, seconds_per_quarter: float = SECONDS_PER_QUARTER):
    """Build the three difficulty tiers' LH Parts from one real
    transcription of the harmony audio — same shape as _rh_variants:
    Easy/Medium derive from the Hard base via quantize_part(max_voices)
    (thinning both note density and simultaneous-voice count) and
    shift_into_range; Hard is the transcription itself, unmodified."""
    notes = extract_lh_notes(harmony_path)
    if not notes:
        raise ValueError("No harmonic content detected")
    base = build_lh_part(notes, seconds_per_quarter)
    return {
        "easy": shift_into_range(quantize_part(base, EASY_GRID, max_voices=1), *EASY_LH_RANGE),
        "medium": shift_into_range(quantize_part(base, MEDIUM_GRID, max_voices=MEDIUM_LH_MAX_VOICES), *MEDIUM_LH_RANGE),
        "hard": base,
    }


def mix_wav_files(path_a: Path, path_b: Path, dest: Path) -> Path:
    """Sum two WAV files sample-for-sample into dest, normalizing to avoid
    clipping. Used to combine the bass+other stems into a single harmony
    signal for LH transcription and key/tempo detection."""
    rate_a, audio_a = wavfile.read(str(path_a))
    _rate_b, audio_b = wavfile.read(str(path_b))

    n = min(len(audio_a), len(audio_b))
    mixed = audio_a[:n].astype(np.float64) + audio_b[:n].astype(np.float64)
    peak = np.max(np.abs(mixed))
    if peak > 0:
        mixed = mixed / peak * 32767

    wavfile.write(str(dest), rate_a, mixed.astype(np.int16))
    return dest


def run_arrange_pipeline(
    job_id: str,
    audio_path: str,
    title: str,
    source_type: str,
    source_url: Optional[str],
    song_id: str,
    dest_dir: Path,
) -> None:
    try:
        set_status(job_id, "separating")
        stems = separate_stems(audio_path, dest_dir / "stems")

        set_status(job_id, "extracting_melody")
        melody_notes = extract_melody_notes(str(stems.vocals))

        set_status(job_id, "detecting_key")
        harmony_path = mix_wav_files(stems.bass, stems.other, dest_dir / "stems" / "harmony.wav")
        detected_key, seconds_per_quarter = detect_key_and_tempo(str(harmony_path))

        set_status(job_id, "arranging")
        lh_variants = _lh_variants(str(harmony_path), seconds_per_quarter)
        rh_variants = _rh_variants(melody_notes, seconds_per_quarter)

        difficulties = {}
        key_signature = key_signature_from_tonic(*detected_key)
        for tier in ("easy", "medium", "hard"):
            score = build_grand_staff_score(rh_variants[tier], lh_variants[tier], title=title, key_signature=key_signature)
            export_musicxml(score, dest_dir / f"{tier}.musicxml")
            difficulties[tier] = {"musicxml_url": f"/storage/{song_id}/{tier}.musicxml"}

        write_metadata(song_id, title=title, source_type=source_type, source_url=source_url, pipeline="arrange")
        evict_oldest_songs()

        set_result(job_id, {"song_id": song_id, "title": title, "difficulties": difficulties})
    except Exception as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        set_failed(job_id, str(exc))
```

- [ ] **Step 4: Update the frontend status label**

In `frontend/src/api/arrange.ts`, change:

```typescript
type ArrangeStage = "separating" | "extracting_melody" | "detecting_chords" | "arranging";

const STAGE_LABELS: Record<ArrangeStage, string> = {
  separating: "Separating vocals and instruments…",
  extracting_melody: "Extracting the melody…",
  detecting_chords: "Detecting chords…",
  arranging: "Arranging the accompaniment…",
};
```

to:

```typescript
type ArrangeStage = "separating" | "extracting_melody" | "detecting_key" | "arranging";

const STAGE_LABELS: Record<ArrangeStage, string> = {
  separating: "Separating vocals and instruments…",
  extracting_melody: "Extracting the melody…",
  detecting_key: "Detecting the key…",
  arranging: "Arranging the accompaniment…",
};
```

- [ ] **Step 5: Delete the retired arrangement package and its tests**

```bash
git rm -r backend/app/arrangement
git rm backend/tests/test_arrangement_easy.py backend/tests/test_arrangement_engine.py backend/tests/test_arrangement_hard.py backend/tests/test_arrangement_medium.py backend/tests/test_arrangement_notation_grid.py backend/tests/test_arrangement_theory.py backend/tests/test_arrangement_consolidation.py
```

- [ ] **Step 6: Run the full backend test suite**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS, zero failures, zero collection errors. Grep the output (or just `grep -r "app.arrangement" backend/app backend/tests`) to confirm nothing still references the deleted package.

- [ ] **Step 7: Run the frontend build**

Run: `cd frontend && npm run build && npm run lint`
Expected: both clean (this changes a `type` union and an object literal — a stale reference anywhere else to `"detecting_chords"` would now be a type error).

- [ ] **Step 8: Real-audio end-to-end verification**

This is the load-bearing check for this whole plan — LH quality now depends on Basic Pitch's actual output on a Demucs "other" stem, which is new territory (see the spec's "Open risk" section). Follow the project's established workflow:

1. Start the local backend: `cd backend && ./.venv/bin/python -m uvicorn app.main:app --port 8000`.
2. Submit each of the 3 cached real songs (paths from the most recent verification run — if stale, use whatever cached separated `mix.wav` files are available, or a fresh audio file):
   - Let It Be, Someone Like You, Fix You — submit via `curl -F "audio_file=@<path>" http://localhost:8000/arrange`, poll `GET /arrange/{job_id}` until done.
3. Convert each resulting MusicXML to MIDI via music21 (`converter.parse(...).write("midi", ...)`) and copy into `~/Downloads/synthony-arrangements/`, clearly named (e.g. `letitbe-easy-v2.mid` — use a `-v2` or similar suffix so these don't overwrite the pre-this-change files already there, which are useful as a before/after comparison).
4. Report on: whether the pipeline completes without errors for all 3 songs × 3 tiers, whether Hard's LH sounds like a plausible harmonic transcription (not silence, not noise, not wildly wrong register) vs. the pre-change Alberti-bass output, and whether Easy/Medium sound like sensible simplifications of Hard.

If real-song output reveals `HARD_MAX_VOICES=4`, the Medium voice cap (`3`), or a register range is clearly wrong, that's expected first-pass tuning (per the spec) — note it, don't silently declare success, and adjust the relevant constant (`app/lh/extract.py::HARD_MAX_VOICES`/`HARD_LH_RANGE`, or `arrange_pipeline.py::MEDIUM_LH_MAX_VOICES`) if the fix is obvious; otherwise report the finding for a listening-based follow-up.

- [ ] **Step 9: Commit**

```bash
git add backend/app/arrange_pipeline.py backend/tests/test_api.py frontend/src/api/arrange.ts
git commit -m "$(cat <<'EOF'
feat: wire up LH true transcription, retire chord-driven arrangement

_lh_variants builds all three LH difficulty tiers from one real
transcription of the harmony (bass+other) stem, mirroring _rh_variants —
Hard is the transcription itself, Easy/Medium derive from it via
quantize_part(max_voices=N) + shift_into_range. Chord-symbol detection,
matching, and the whole chord-driven arrangement/ package are retired;
detect_key_and_tempo replaces detect_chords.
EOF
)"
```

---

## Deferred (per the design spec, not in scope here)

- Any onset-cleanup/legato pass for the LH transcription (only add one if real-song listening in Task 4 Step 8 surfaces fragmented onsets).
- Distinguishing multiple simultaneous instruments within Demucs's "other" stem (the spec's noted open risk) — not solvable in this pass.
- Further tuning of `HARD_MAX_VOICES`, the Medium voice cap, or the register ranges beyond what Task 4's real-audio check surfaces as an obvious fix — expect a follow-up by-ear tuning round.
