# Real Tempo Detection for Spec 2 (Phase 5 quality) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thread the song's *real* detected tempo through Spec 2's timing
math instead of the fixed 120 BPM assumption every Spec 2 function
currently hardcodes — by-ear feedback (Phase 5) reported the arrangement
rhythm feels "stiff," and `app/chords/detect.py` already computes the
real tempo via `librosa.beat.beat_track` and then throws it away.

**Architecture:** `detect_chords` starts returning `(chords, seconds_per_quarter)`
instead of just `chords`. Every Spec 2 function that currently converts
seconds→quarterLength using the fixed `SECONDS_PER_QUARTER` constant
(imported from `app.notation.hand_split`) gains an optional
`seconds_per_quarter` parameter defaulting to that same constant — so
every existing caller (tests, and anything not yet updated) keeps
behaving exactly as before, while `arrange_pipeline.py` passes the real,
song-specific value through the whole chain. **Spec 1 is completely
unaffected** — its fixed-tempo assumption is explicitly out of scope and
untouched; only Spec 2's own functions gain the new parameter.

**Tech Stack:** Python, `librosa` (existing dependency, `beat_track`
already called), `numpy`.

**Spec:** No formal design doc for this — this is direct Phase 5 by-ear
tuning work agreed in conversation. Reference:
`docs/superpowers/specs/2026-09-01-any-song-arrangement-design.md` for
overall pipeline context if anything here is ambiguous (it shouldn't be).

## Global Constraints

- Every changed function signature adds `seconds_per_quarter` as an
  **optional** parameter with a default of `SECONDS_PER_QUARTER` (from
  `app.notation.hand_split`) — this is additive, not breaking. No
  existing call site (test or production) should need to change *unless*
  it specifically needs the new tempo-aware behavior.
- The one **breaking** change in this plan is `detect_chords`'s return
  type (`list[ChordSymbol]` → `tuple[list[ChordSymbol], float]`) — every
  call site (production and test) must be updated for that one.
- Tempo is clamped to a musically sane range (60-200 BPM) before
  converting to seconds-per-quarter — beat-tracking on noisy or atypical
  audio occasionally returns implausible outliers (near-zero, or
  half/double-tempo errors), and an unclamped value could produce
  absurdly stretched or compressed timing.
- `quantize_part`/`shift_into_range` (Spec 1's difficulty engine,
  reused by Spec 2's `_rh_variants` in `arrange_pipeline.py`) are **not
  touched** — they already operate purely in quarterLength space with no
  seconds conversion, so they're already tempo-agnostic.

---

## File Structure

- Modify: `app/chords/detect.py` (`detect_chords` returns tempo too; new
  `_tempo_to_seconds_per_quarter` helper)
- Modify: `app/notation/hand_split.py` (`_to_music21_note`, `notes_to_part`
  gain the optional parameter — `notes_to_grand_staff` and everything
  else in this file is untouched)
- Modify: `app/melody/extract.py` (`quantize_melody`, `build_melody_part`)
- Modify: `app/arrangement/easy.py`, `medium.py`, `hard.py` (`to_easy_lh`,
  `to_medium_lh`, `to_hard_lh`)
- Modify: `app/arrangement/engine.py` (`generate_lh_variants`)
- Modify: `app/arrange_pipeline.py` (`_rh_variants`, `run_arrange_pipeline`
  — capture and thread the real tempo through)
- Modify: `backend/tests/test_chords_detect.py`,
  `test_arrangement_easy.py`, `test_arrangement_medium.py`,
  `test_arrangement_hard.py`, `test_melody_quantize.py`,
  `test_hand_split.py`, `test_api.py`

## Task 1: `detect_chords` returns real tempo

**Files:**
- Modify: `app/chords/detect.py`
- Modify: `backend/tests/test_chords_detect.py`

**Interfaces:**
- Produces: `_tempo_to_seconds_per_quarter(tempo) -> float` — converts a
  detected BPM value (possibly a numpy scalar/array, possibly `None` or
  `0`) to seconds-per-quarter-note, clamped to `[60, 200]` BPM, falling
  back to `0.5` (120 BPM) if the input is falsy/unusable.
- Modifies: `detect_chords(audio_path: str) -> tuple[list[ChordSymbol], float]`
  — now returns `(chords, seconds_per_quarter)`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_chords_detect.py` (near the top, alongside the
existing imports):

```python
from app.chords.detect import (
    _absorb_short_chords,
    _merge_consecutive,
    _tempo_to_seconds_per_quarter,
    detect_chords,
)


def test_tempo_to_seconds_per_quarter_converts_bpm():
    assert _tempo_to_seconds_per_quarter(120.0) == 0.5
    assert _tempo_to_seconds_per_quarter(60.0) == 1.0


def test_tempo_to_seconds_per_quarter_clamps_extreme_values():
    assert _tempo_to_seconds_per_quarter(20.0) == 60.0 / 60.0   # clamped up to MIN_TEMPO_BPM
    assert _tempo_to_seconds_per_quarter(500.0) == 60.0 / 200.0  # clamped down to MAX_TEMPO_BPM


def test_tempo_to_seconds_per_quarter_falls_back_on_zero_or_none():
    assert _tempo_to_seconds_per_quarter(0.0) == 0.5
    assert _tempo_to_seconds_per_quarter(None) == 0.5
```

Replace the existing `from app.chords.detect import _absorb_short_chords, _merge_consecutive, detect_chords`
import line (if present separately) with the one above — don't leave a
duplicate import.

Then update `test_detect_chords_returns_a_sequence_covering_the_clip` to
unpack the new tuple return:

```python
def test_detect_chords_returns_a_sequence_and_tempo_covering_the_clip(synthetic_piano_wav):
    chords, seconds_per_quarter = detect_chords(str(synthetic_piano_wav))

    assert len(chords) >= 1
    assert chords[0].start == 0.0
    assert chords[-1].start + chords[-1].duration <= 2.5  # clip is 2s, allow rounding slack
    for chord in chords:
        assert 0 <= chord.root <= 11
        assert chord.quality in ("major", "minor", "dim", "dom7", "maj7", "min7")
    assert seconds_per_quarter > 0
```

(This replaces the old `test_detect_chords_returns_a_sequence_covering_the_clip`
— same body, renamed, plus the tempo unpack/assertion.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_detect.py -v`
Expected: FAIL — `ImportError: cannot import name '_tempo_to_seconds_per_quarter'`
for the three new tests, and a tuple-unpacking `ValueError` (or similar)
for the renamed test since `detect_chords` still returns a bare list.

- [ ] **Step 3: Write minimal implementation**

In `app/chords/detect.py`, add these constants near the existing
`BEATS_PER_BAR`/`MIN_CHORD_DURATION`:

```python
MIN_TEMPO_BPM = 60.0
MAX_TEMPO_BPM = 200.0
DEFAULT_SECONDS_PER_QUARTER = 0.5  # 120 BPM fallback if beat-tracking yields nothing usable
```

Add this function (anywhere in the module, e.g. right after the
constants):

```python
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
```

Change `detect_chords`'s body (the `tempo, beat_frames = librosa.beat.beat_track(...)`
line and the final `return` statement) to:

```python
def detect_chords(audio_path: str) -> tuple[list[ChordSymbol], float]:
    """Detect a chord-per-bar sequence from an audio file, along with the
    song's own detected tempo (as seconds-per-quarter-note) so callers can
    convert chord/melody timing using the song's real tempo instead of a
    fixed assumption. Chroma features aggregated over 4-beat bars,
    matched against chord templates, with consecutive identical chords
    merged and short blips absorbed into their neighbor."""
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration = len(y) / sr

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    seconds_per_quarter = _tempo_to_seconds_per_quarter(tempo)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    bar_starts = list(beat_times[::BEATS_PER_BAR])
    if not bar_starts or bar_starts[0] > 0:
        bar_starts.insert(0, 0.0)
    bar_starts.append(duration)

    chroma_times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr)

    raw_chords: list[ChordSymbol] = []
    for start, end in zip(bar_starts[:-1], bar_starts[1:]):
        if end <= start:
            continue
        in_bar = (chroma_times >= start) & (chroma_times < end)
        if not np.any(in_bar):
            continue
        bar_chroma = chroma[:, in_bar].mean(axis=1)
        root, quality = match_chord(bar_chroma)
        raw_chords.append(ChordSymbol(start=float(start), duration=float(end - start), root=root, quality=quality))

    chords = _absorb_short_chords(_merge_consecutive(raw_chords))
    return chords, seconds_per_quarter
```

(Everything else in the file — `_merge_consecutive`, `_absorb_short_chords`
— stays exactly as-is.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_detect.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Update the one other place `detect_chords` is called**

`app/arrange_pipeline.py` currently does `chords = detect_chords(str(harmony_path))`.
This will break at import/runtime until Task 6 updates it — that's
expected and fine to leave broken until Task 6 in this same plan; don't
try to fix it here. Confirm you understand this by running the full
suite now and observing failures **only** in `test_api.py`'s arrange
tests and nowhere else:

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: failures isolated to `test_arrange_full_job_lifecycle_returns_transcribe_shaped_result`
and `test_arrange_job_failure_sets_failed_status_with_detail` in
`test_api.py` (both will be fixed in Task 6) — every other test file
passes.

- [ ] **Step 6: Commit**

```bash
git add app/chords/detect.py backend/tests/test_chords_detect.py
git commit -m "feat: detect_chords returns the song's real tempo"
```

(Adjust the `git add` paths if your working directory is already
`backend/` — the plan writes paths relative to the repo root.)

## Task 2: Thread `seconds_per_quarter` through `hand_split.py` and `melody/extract.py`

**Files:**
- Modify: `app/notation/hand_split.py`
- Modify: `app/melody/extract.py`
- Modify: `backend/tests/test_hand_split.py`
- Modify: `backend/tests/test_melody_quantize.py`

**Interfaces:**
- Modifies: `_to_music21_note(event: NoteEvent, seconds_per_quarter: float = SECONDS_PER_QUARTER) -> note.Note`
  in `hand_split.py` — used internally by both `notes_to_grand_staff`
  (Spec 1, calls it with no second argument, so behavior is byte-for-byte
  identical to before) and `notes_to_part` (Spec 2).
- Modifies: `notes_to_part(notes: list[NoteEvent], part_id: str = "RH", seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part`
- Modifies: `quantize_melody(notes: list[NoteEvent], grid: float, seconds_per_quarter: float = SECONDS_PER_QUARTER) -> list[NoteEvent]`
  in `melody/extract.py`
- Modifies: `build_melody_part(notes: list[NoteEvent], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_hand_split.py`:

```python
def test_notes_to_part_respects_a_non_default_tempo():
    notes = [NoteEvent(start=0.0, end=1.0, pitch=60)]
    part = notes_to_part(notes, seconds_per_quarter=1.0)  # 60 BPM instead of the 120 BPM default
    result_notes = list(part.flatten().notes)
    assert result_notes[0].duration.quarterLength == 1.0  # 1s / 1.0s-per-quarter, vs 2.0 at the default tempo
```

(This requires `notes_to_part` already be imported in the test file —
check the existing import line and add `notes_to_part` to it if it's not
already there.)

Add to `backend/tests/test_melody_quantize.py`:

```python
def test_quantize_melody_respects_a_non_default_tempo():
    # At 1.0 seconds-per-quarter (60 BPM), a quarter-note grid slot is
    # 1.0s wide instead of the default 0.5s — these two onsets land in
    # different slots at the default tempo but the same slot at this one.
    notes = [
        NoteEvent(start=0.0, end=0.1, pitch=60),
        NoteEvent(start=0.6, end=0.7, pitch=62),
    ]
    result = quantize_melody(notes, QUARTER_GRID, seconds_per_quarter=1.0)
    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_hand_split.py tests/test_melody_quantize.py -v -k tempo`
Expected: FAIL — `TypeError: notes_to_part() got an unexpected keyword argument 'seconds_per_quarter'`
and the equivalent for `quantize_melody`.

- [ ] **Step 3: Write minimal implementation**

In `app/notation/hand_split.py`, change `_to_music21_note`:

```python
def _to_music21_note(event: NoteEvent, seconds_per_quarter: float = SECONDS_PER_QUARTER) -> note.Note:
    m21_note = note.Note()
    m21_note.pitch.midi = event.pitch
    duration = (event.end - event.start) / seconds_per_quarter
    duration = max(duration, NOTATION_GRID)
    m21_note.duration.quarterLength = _round_to_grid(duration, NOTATION_GRID)
    return m21_note
```

And `notes_to_part`:

```python
def notes_to_part(notes: list[NoteEvent], part_id: str = "RH", seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """Build a single-line Part from a flat list of NoteEvents, e.g. an
    already-reduced monophonic melody line. Unlike notes_to_grand_staff,
    this does no RH/LH splitting — every note goes into one Part, in
    onset order."""
    part = stream.Part(id=part_id)
    part.append(clef.TrebleClef())
    for event in sorted(notes, key=lambda e: e.start):
        offset = _round_to_grid(event.start / seconds_per_quarter, NOTATION_GRID)
        part.insert(offset, _to_music21_note(event, seconds_per_quarter))
    return part
```

Leave every other function in this file — especially `notes_to_grand_staff`,
which must keep calling `_to_music21_note(event)` with no second argument
— completely untouched.

In `app/melody/extract.py`, change `quantize_melody`:

```python
def quantize_melody(notes: list[NoteEvent], grid: float, seconds_per_quarter: float = SECONDS_PER_QUARTER) -> list[NoteEvent]:
    """Snap note onsets to `grid` (in quarterLength units — 1.0 = quarter
    note, 0.5 = eighth, etc.) at the given tempo, drop duplicate
    re-attacks that land in the same grid slot, and legato each kept note
    into the next one's onset so the melody sustains instead of stopping
    short. The last note is floored to at least one grid step, so it
    isn't left too short to register when nothing follows it to legato
    into."""
    grid_seconds = grid * seconds_per_quarter
    ordered = sorted(notes, key=lambda n: n.start)

    kept: list[NoteEvent] = []
    seen_slots: set[int] = set()
    for candidate in ordered:
        slot = round(candidate.start / grid_seconds)
        if slot in seen_slots:
            continue
        seen_slots.add(slot)
        kept.append(NoteEvent(start=slot * grid_seconds, end=candidate.end, pitch=candidate.pitch, velocity=candidate.velocity))

    for i in range(len(kept) - 1):
        if kept[i].end < kept[i + 1].start:
            kept[i] = NoteEvent(start=kept[i].start, end=kept[i + 1].start, pitch=kept[i].pitch, velocity=kept[i].velocity)

    if kept and kept[-1].end - kept[-1].start < grid_seconds:
        last = kept[-1]
        kept[-1] = NoteEvent(start=last.start, end=last.start + grid_seconds, pitch=last.pitch, velocity=last.velocity)

    return kept
```

(Only the signature and the `grid_seconds = grid * seconds_per_quarter`
line change — the rest of the function body is identical to before.)

And `build_melody_part`:

```python
def build_melody_part(notes: list[NoteEvent], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """Clean up a reduced melody note list (legato, de-fragmented) and
    build the resulting RH Part. This is the full-detail base every
    difficulty tier derives from."""
    return notes_to_part(quantize_melody(notes, CLEANUP_GRID, seconds_per_quarter), part_id="RH", seconds_per_quarter=seconds_per_quarter)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_hand_split.py tests/test_melody_quantize.py tests/test_melody_extract.py -v`
Expected: PASS (the full contents of all three files — confirms nothing
in `notes_to_grand_staff`'s Spec 1 behavior regressed)

- [ ] **Step 5: Commit**

```bash
git add app/notation/hand_split.py app/melody/extract.py backend/tests/test_hand_split.py backend/tests/test_melody_quantize.py
git commit -m "feat: thread real tempo through notes_to_part and melody quantization"
```

## Task 3: Thread `seconds_per_quarter` through the arrangement engine

**Files:**
- Modify: `app/arrangement/easy.py`, `medium.py`, `hard.py`, `engine.py`
- Modify: `backend/tests/test_arrangement_easy.py`,
  `test_arrangement_medium.py`, `test_arrangement_hard.py`

**Interfaces:**
- Modifies: `to_easy_lh(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part`
- Modifies: `to_medium_lh(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part`
- Modifies: `to_hard_lh(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part`
- Modifies: `generate_lh_variants(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> ArrangementVariants`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_arrangement_easy.py`:

```python
def test_easy_lh_respects_a_non_default_tempo():
    chords = [ChordSymbol(start=0.0, duration=2.0, root=0, quality="major")]
    part = to_easy_lh(chords, seconds_per_quarter=1.0)  # 60 BPM instead of the 120 BPM default
    notes = list(part.flatten().notes)
    assert notes[0].duration.quarterLength == 2.0  # 2s / 1.0s-per-quarter, vs 4.0 at the default tempo
```

Add to `backend/tests/test_arrangement_medium.py`:

```python
def test_medium_lh_respects_a_non_default_tempo():
    chords = [ChordSymbol(start=0.0, duration=2.0, root=0, quality="major")]
    part = to_medium_lh(chords, seconds_per_quarter=1.0)
    notes = list(part.flatten().notes)
    assert notes[0].duration.quarterLength == 2.0  # vs 4.0 at the default tempo
```

Add to `backend/tests/test_arrangement_hard.py`:

```python
def test_hard_lh_arpeggio_step_offsets_respect_a_non_default_tempo():
    # duration=4.0s at 1.0 seconds-per-quarter (60 BPM) is a long chord
    # (still >= SHORT_CHORD_THRESHOLD in real seconds) with only 4
    # eighth-note steps fitting in it, vs 8 at the default 120 BPM tempo.
    chords = [ChordSymbol(start=0.0, duration=4.0, root=0, quality="major")]
    part = to_hard_lh(chords, seconds_per_quarter=1.0)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    assert len(notes) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrangement_easy.py tests/test_arrangement_medium.py tests/test_arrangement_hard.py -v -k tempo`
Expected: FAIL — `TypeError: to_easy_lh() got an unexpected keyword argument 'seconds_per_quarter'`
(and equivalent for the other two)

- [ ] **Step 3: Write minimal implementation**

In `app/arrangement/easy.py`, change the signature and body:

```python
def to_easy_lh(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """One root note per chord, held for the chord's full duration."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    for chord in chords:
        offset = round_to_grid(chord.start / seconds_per_quarter)
        length = quantized_duration(chord.duration, seconds_per_quarter)
        midi = pitch_class_to_midi_in_range(chord.root, *EASY_LH_RANGE)
        n = note.Note()
        n.pitch.midi = midi
        n.duration.quarterLength = length
        part.insert(offset, n)
    return part
```

In `app/arrangement/medium.py`:

```python
def to_medium_lh(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """A close-position block chord (root + third + fifth) per chord,
    held for the chord's full duration."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    for chord in chords:
        offset = round_to_grid(chord.start / seconds_per_quarter)
        length = quantized_duration(chord.duration, seconds_per_quarter)
        tones = chord_tones(chord.root, chord.quality)[:MAX_BLOCK_TONES]
        root_midi = pitch_class_to_midi_in_range(tones[0], *MEDIUM_LH_RANGE)
        for pitch_class in tones:
            n = note.Note()
            n.pitch.midi = stack_above(root_midi, pitch_class)
            n.duration.quarterLength = length
            part.insert(offset, n)
    return part
```

In `app/arrangement/hard.py`, change the signature and the `step_seconds`
line (everything else in the function stays the same):

```python
def to_hard_lh(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """A full block chord for short chords, an Alberti-bass arpeggio
    (root-fifth-third-fifth, subdivided into eighth notes) for longer
    ones — variety instead of one repeating pattern regardless of
    context."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    step_seconds = ARPEGGIO_STEP * seconds_per_quarter

    for chord in chords:
        tones = chord_tones(chord.root, chord.quality)
        root_midi = pitch_class_to_midi_in_range(tones[0], *HARD_LH_RANGE)

        if chord.duration < SHORT_CHORD_THRESHOLD:
            offset = round_to_grid(chord.start / seconds_per_quarter)
            length = quantized_duration(chord.duration, seconds_per_quarter)
            for pitch_class in tones:
                n = note.Note()
                n.pitch.midi = stack_above(root_midi, pitch_class)
                n.duration.quarterLength = length
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
            part.insert(offset, n)

            step += 1
            elapsed += step_seconds

    return part
```

In `app/arrangement/engine.py`, change `generate_lh_variants`:

```python
def generate_lh_variants(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> ArrangementVariants:
    return ArrangementVariants(
        easy=to_easy_lh(chords, seconds_per_quarter),
        medium=to_medium_lh(chords, seconds_per_quarter),
        hard=to_hard_lh(chords, seconds_per_quarter),
    )
```

Add `from app.notation.hand_split import SECONDS_PER_QUARTER` to
`engine.py`'s imports (it doesn't currently import this).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrangement_easy.py tests/test_arrangement_medium.py tests/test_arrangement_hard.py tests/test_arrangement_engine.py -v`
Expected: PASS (full contents of all four files)

- [ ] **Step 5: Commit**

```bash
git add app/arrangement/easy.py app/arrangement/medium.py app/arrangement/hard.py app/arrangement/engine.py backend/tests/test_arrangement_easy.py backend/tests/test_arrangement_medium.py backend/tests/test_arrangement_hard.py
git commit -m "feat: thread real tempo through the arrangement engine"
```

## Task 4: Wire the real tempo through `arrange_pipeline.py`

**Files:**
- Modify: `app/arrange_pipeline.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Modifies: `_rh_variants(melody_notes, seconds_per_quarter: float = SECONDS_PER_QUARTER) -> dict`
- Modifies: `run_arrange_pipeline(...)` — unpacks `detect_chords`'s new
  tuple return and passes the real tempo into `generate_lh_variants` and
  `_rh_variants`.

- [ ] **Step 1: Update the failing production code**

In `app/arrange_pipeline.py`, change `_rh_variants`:

```python
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
```

And change the two lines in `run_arrange_pipeline` that call
`detect_chords` and build the variants:

```python
        set_status(job_id, "detecting_chords")
        harmony_path = mix_wav_files(stems.bass, stems.other, dest_dir / "stems" / "harmony.wav")
        chords, seconds_per_quarter = detect_chords(str(harmony_path))
        if not chords:
            raise ValueError("No chords detected")

        set_status(job_id, "arranging")
        variants = generate_lh_variants(chords, seconds_per_quarter)
        rh_variants = _rh_variants(melody_notes, seconds_per_quarter)
```

Add `from app.notation.hand_split import SECONDS_PER_QUARTER, build_grand_staff_score`
(merge with the existing `hand_split` import line rather than duplicating
it) so `_rh_variants`'s default parameter value resolves.

- [ ] **Step 2: Update the test that monkeypatches `detect_chords`**

In `backend/tests/test_api.py`, find
`test_arrange_full_job_lifecycle_returns_transcribe_shaped_result` and
change its `detect_chords` monkeypatch to return the new tuple shape:

```python
    monkeypatch.setattr(
        pipeline_module, "detect_chords",
        lambda audio_path: ([ChordSymbol(start=0.0, duration=1.0, root=0, quality="major")], 0.5),
    )
```

(Only this one `monkeypatch.setattr` call changes — everything else in
that test stays the same. The other arrange test,
`test_arrange_job_failure_sets_failed_status_with_detail`, monkeypatches
`separate_stems` to fail before `detect_chords` is ever called, so it
needs no change.)

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -v -k arrange`
Expected: PASS (all 3 arrange tests)

- [ ] **Step 4: Run the full backend test suite**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all tests pass — this is the first point where the whole
tempo-threading change is exercised end-to-end together.

- [ ] **Step 5: Commit**

```bash
git add app/arrange_pipeline.py backend/tests/test_api.py
git commit -m "feat: wire the song's real detected tempo through the arrange pipeline"
```

## Task 5: Verify against a real song

**Files:** none — this task runs the already-committed code against real
audio to confirm the tempo actually changes per-song, the way Task 1-4
of the previous quality-fix plans did.

- [ ] **Step 1: Run `detect_chords` against one of the real spike-song
  harmony stems already on disk and print the detected tempo**

If the coordinator (main session) has already generated arrange-pipeline
output for real songs, harmony stems will exist under
`backend/storage/<song_id>/stems/harmony.wav`. Find one with:

```bash
find backend/storage -name harmony.wav | head -3
```

Then, from `backend/`:

```bash
./.venv/bin/python -c "
from app.chords.detect import detect_chords
chords, seconds_per_quarter = detect_chords('storage/<a song_id from above>/stems/harmony.wav')
print('seconds_per_quarter:', seconds_per_quarter)
print('implied BPM:', 60.0 / seconds_per_quarter)
print('chord count:', len(chords))
"
```

Expected: a BPM value that is plausible for the song (not exactly 120.0
unless the real song genuinely is ~120 BPM) and confirms the clamp/
fallback logic didn't silently produce the old fixed default. Report
this in your final summary — if no `harmony.wav` files exist yet in
storage, note that and skip this step rather than generating new ones
(that's the coordinator's job with real song files, not this agent's).

## Out of Scope for This Plan

- Dynamics/expression (velocity passthrough) and key-aware chord
  smoothing — separate, parallel plans building on this one's final
  interface.
- Richer arrangement texture (fuller voicings, pedal simulation, walking
  bass, chord vocabulary expansion) — later, bigger work once the
  foundation (this plan, dynamics, key-awareness) is solid.
- Actually re-tuning `MIN_CHORD_DURATION`, `SHORT_CHORD_THRESHOLD`, or
  `CYCLES_BETWEEN_OCTAVE_LIFTS` (currently expressed in real seconds) to
  be tempo-relative (e.g. "N bars" instead of "N seconds") — worth
  reconsidering once real tempo is flowing through, but not part of this
  plan; those constants keep their current absolute-seconds meaning here.
