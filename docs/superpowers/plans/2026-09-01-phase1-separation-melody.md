# Separation + Melody Extraction (Spec 2, Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two independently-testable pieces of Spec 2 Phase 1:
(1) a stem-separation module wrapping Demucs, and (2) a melody-extraction
module that runs the existing Basic Pitch wrapper against a vocal-isolated
audio file and reduces its polyphonic output to a single RH melody
`Part`.

**Architecture:** Two new packages, `backend/app/separation/` and
`backend/app/melody/`. Neither imports the other — both operate on a
plain audio-file path, so they're independently buildable/testable and
only get wired together later (in the Phase 4 async job). This mirrors
how `backend/app/arrangement/` was kept decoupled from chord *recognition*
in the Phase 3 plan.

**Tech Stack:** Python, `demucs` (new dependency — CLI invoked via
subprocess), `basic-pitch` (existing, unmodified), `music21`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-01-any-song-arrangement-design.md`
(see "New Components" → Stem separation / Melody extraction, "Phased
Roadmap" → Phase 1, "Testing Strategy").

**Phase 0 spike findings this plan builds on** (see prior spike report):
Demucs (`htdemucs` model) separates cleanly on CPU in ~10-15s for a
45s clip — fast enough for an async job, no GPU needed. The model
checkpoint is already cached at `~/.cache/torch/hub/checkpoints/` on this
machine from the spike run, so no re-download should be needed.

## Global Constraints

- Basic Pitch itself (`app/transcription/audio_to_midi.py`) is reused
  **unmodified** — melody extraction is a new reduction step on top of
  its existing output, per the spec's "New Components" section.
- Deterministic, non-ML reduction heuristic for monophonic collapse (no
  training data) — consistent with the rest of the codebase's testable,
  inspectable style.
- Time values follow the codebase's existing fixed-tempo assumption
  (`SECONDS_PER_QUARTER = 0.5`, 120 BPM) already defined in
  `app.notation.hand_split` — do not redefine it.
- Add `demucs` to `backend/requirements.txt`; do not add any other new
  dependency (librosa, numpy, scipy are already present).
- Tests: the monophonic-reduction heuristic is a pure function tested with
  hand-crafted `NoteEvent` lists and exact expected output. The two
  audio-facing integration tests (separation, melody extraction) reuse the
  existing `synthetic_piano_wav` pytest fixture in
  `backend/tests/conftest.py` and are loosely asserted, per the spec's
  Testing Strategy and matching the existing pattern in
  `backend/tests/test_audio_to_midi.py`.

---

## File Structure

- Modify: `backend/requirements.txt` (add `demucs`)
- Create: `backend/app/separation/__init__.py`
- Create: `backend/app/separation/types.py` — `Stems` dataclass
- Create: `backend/app/separation/separator.py` — `separate_stems`
- Create: `backend/tests/test_separator.py`
- Modify: `backend/app/notation/hand_split.py` (add `notes_to_part`,
  inserted after the existing `notes_to_grand_staff` function, around
  line 158 — nothing existing in this file changes)
- Create: `backend/app/melody/__init__.py`
- Create: `backend/app/melody/extract.py` — `reduce_to_monophonic`,
  `extract_melody_part`
- Create: `backend/tests/test_melody_extract.py`

## Task 1: Stem separation module

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/app/separation/__init__.py`
- Create: `backend/app/separation/types.py`
- Create: `backend/app/separation/separator.py`
- Test: `backend/tests/test_separator.py`

**Interfaces:**
- Produces: `Stems(vocals: Path, drums: Path, bass: Path, other: Path)`
- Produces: `separate_stems(audio_path: str, output_dir: Path) -> Stems`
  — runs Demucs 4-stem separation, writes `vocals.wav` / `drums.wav` /
  `bass.wav` / `other.wav` under `output_dir`, returns their paths. Raises
  `subprocess.CalledProcessError` on separation failure (nothing catches
  it here — the caller, e.g. the Phase 4 job runner, decides how to
  surface that as a job failure).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_separator.py
from scipy.io import wavfile

from app.separation.separator import separate_stems


def test_separate_stems_produces_all_four_stems_matching_input_duration(synthetic_piano_wav, tmp_path):
    input_rate, input_audio = wavfile.read(str(synthetic_piano_wav))
    input_duration = len(input_audio) / input_rate

    stems = separate_stems(str(synthetic_piano_wav), tmp_path / "separated")

    for stem_path in (stems.vocals, stems.drums, stems.bass, stems.other):
        assert stem_path.exists()
        rate, audio = wavfile.read(str(stem_path))
        duration = len(audio) / rate
        assert abs(duration - input_duration) < 0.5  # Demucs may pad slightly
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_separator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.separation'`

- [ ] **Step 3: Add the dependency**

Add a `demucs` line to `backend/requirements.txt` (alongside the existing
`basic-pitch[onnx]` / `librosa` lines). Then install it into the venv:

```bash
cd backend && ./.venv/bin/python -m pip install demucs
```

(Note: `.venv/bin/pip`'s shebang may point to a stale path in this repo —
use `./.venv/bin/python -m pip install ...` instead of `./.venv/bin/pip
install ...` if `pip` itself fails to run.)

- [ ] **Step 4: Write minimal implementation**

```python
# backend/app/separation/types.py
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Stems:
    vocals: Path
    drums: Path
    bass: Path
    other: Path
```

```python
# backend/app/separation/separator.py
import subprocess
import sys
from pathlib import Path

from app.separation.types import Stems

MODEL_NAME = "htdemucs"
STEM_NAMES = ("vocals", "drums", "bass", "other")


def separate_stems(audio_path: str, output_dir: Path) -> Stems:
    """Run Demucs 4-stem separation on audio_path, writing vocals/drums/
    bass/other WAV files under output_dir, and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [sys.executable, "-m", "demucs.separate", "-n", MODEL_NAME, "-o", str(output_dir), audio_path],
        check=True,
        capture_output=True,
    )

    track_name = Path(audio_path).stem
    stem_dir = output_dir / MODEL_NAME / track_name
    paths = {name: stem_dir / f"{name}.wav" for name in STEM_NAMES}
    return Stems(**paths)
```

```bash
touch backend/app/separation/__init__.py
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_separator.py -v`
Expected: PASS (this will take several seconds — real Demucs inference
runs on the 2-second fixture clip)

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/separation/ backend/tests/test_separator.py
git commit -m "feat: add Demucs-based stem separation module"
```

## Task 2: `notes_to_part` helper and monophonic-reduction heuristic

**Files:**
- Modify: `backend/app/notation/hand_split.py` (add a new function; do not
  change any existing function)
- Create: `backend/app/melody/__init__.py`
- Create: `backend/app/melody/extract.py` (just `reduce_to_monophonic` in
  this task — `extract_melody_part` is added in Task 3)
- Test: `backend/tests/test_melody_extract.py` (just the
  `reduce_to_monophonic` tests in this task)

**Interfaces:**
- Consumes (from `app.notation.hand_split`, already defined):
  `_to_music21_note`, `_seconds_to_quarter_length`, `_round_to_grid`,
  `NOTATION_GRID` (all private module-level helpers in that file — the
  new function lives in the same module, so it calls them directly).
- Produces: `notes_to_part(notes: list[NoteEvent], part_id: str = "RH") -> stream.Part`
  in `app.notation.hand_split` — builds a single-line `Part` from a flat
  list of `NoteEvent`s in onset order, with no RH/LH splitting (unlike
  `notes_to_grand_staff`, which does).
- Produces: `reduce_to_monophonic(notes: list[NoteEvent]) -> list[NoteEvent]`
  in `app.melody.extract`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_melody_extract.py
from app.melody.extract import reduce_to_monophonic
from app.notation.types import NoteEvent


def test_reduce_to_monophonic_passes_through_non_overlapping_notes():
    notes = [
        NoteEvent(start=0.0, end=0.5, pitch=60),
        NoteEvent(start=0.5, end=1.0, pitch=62),
    ]
    assert reduce_to_monophonic(notes) == notes


def test_reduce_to_monophonic_keeps_higher_pitch_when_notes_overlap():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=60),  # discarded — overlaps, lower
        NoteEvent(start=0.2, end=0.8, pitch=67),   # kept — higher pitch
    ]
    assert reduce_to_monophonic(notes) == [notes[1]]


def test_reduce_to_monophonic_discards_lower_pitch_overlapping_note():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=67),  # kept — higher pitch, processed first
        NoteEvent(start=0.2, end=0.5, pitch=60),   # discarded — overlaps, lower
    ]
    assert reduce_to_monophonic(notes) == [notes[0]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_melody_extract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.melody'`

- [ ] **Step 3: Add `notes_to_part` to `hand_split.py`**

Insert this function immediately after the existing `notes_to_grand_staff`
function (which ends around line 157 of
`backend/app/notation/hand_split.py`, right before `get_title`). Do not
modify anything else in the file:

```python
def notes_to_part(notes: list[NoteEvent], part_id: str = "RH") -> stream.Part:
    """Build a single-line Part from a flat list of NoteEvents, e.g. an
    already-reduced monophonic melody line. Unlike notes_to_grand_staff,
    this does no RH/LH splitting — every note goes into one Part, in
    onset order."""
    part = stream.Part(id=part_id)
    part.append(clef.TrebleClef())
    for event in sorted(notes, key=lambda e: e.start):
        offset = _round_to_grid(_seconds_to_quarter_length(event.start), NOTATION_GRID)
        part.insert(offset, _to_music21_note(event))
    return part
```

- [ ] **Step 4: Write `reduce_to_monophonic`**

```python
# backend/app/melody/extract.py
from app.notation.types import NoteEvent


def reduce_to_monophonic(notes: list[NoteEvent]) -> list[NoteEvent]:
    """Collapse polyphonic note detections to a single melody line: when
    two notes overlap in time, keep only the higher-pitched one (the
    sung/played melody is assumed to be the top voice), discarding the
    other entirely."""
    ordered = sorted(notes, key=lambda n: n.start)
    melody: list[NoteEvent] = []
    for candidate in ordered:
        if melody and candidate.start < melody[-1].end:
            if candidate.pitch > melody[-1].pitch:
                melody[-1] = candidate
        else:
            melody.append(candidate)
    return melody
```

```bash
touch backend/app/melody/__init__.py
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_melody_extract.py tests/test_hand_split.py -v`
Expected: PASS — the new `reduce_to_monophonic` tests pass, and the
existing `test_hand_split.py` suite still passes unchanged (confirms the
`hand_split.py` addition didn't disturb existing behavior).

- [ ] **Step 6: Commit**

```bash
git add backend/app/notation/hand_split.py backend/app/melody/__init__.py backend/app/melody/extract.py backend/tests/test_melody_extract.py
git commit -m "feat: add notes_to_part helper and monophonic melody reduction"
```

## Task 3: `extract_melody_part` — the module's public entry point

**Files:**
- Modify: `backend/app/melody/extract.py` (add `extract_melody_part`)
- Test: `backend/tests/test_melody_extract.py` (add the integration test)

**Interfaces:**
- Consumes: `transcribe_audio_to_notes` (existing, unmodified, from
  `app.transcription.audio_to_midi`), `reduce_to_monophonic` (Task 2),
  `notes_to_part` (Task 2, from `app.notation.hand_split`).
- Produces: `extract_melody_part(audio_path: str) -> stream.Part` — runs
  Basic Pitch on `audio_path` (typically a vocal-isolated stem from Task
  1's `separate_stems`, though this function doesn't know or care where
  the audio came from), reduces to monophonic, returns an RH `Part`.

- [ ] **Step 1: Write the failing test**

```python
# add to backend/tests/test_melody_extract.py
from app.melody.extract import extract_melody_part


def test_extract_melody_part_detects_note_near_a4(synthetic_piano_wav):
    part = extract_melody_part(str(synthetic_piano_wav))
    notes = list(part.flatten().notes)

    assert len(notes) >= 1
    pitches = [n.pitch.midi for n in notes]
    assert any(abs(p - 69) <= 2 for p in pitches)  # A4 = MIDI 69, +/-2 semitone tolerance
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_melody_extract.py -v -k extract_melody_part`
Expected: FAIL with `ImportError: cannot import name 'extract_melody_part'`

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/melody/extract.py` (append — keep `reduce_to_monophonic`
as-is):

```python
from music21 import stream

from app.notation.hand_split import notes_to_part
from app.transcription.audio_to_midi import transcribe_audio_to_notes


def extract_melody_part(audio_path: str) -> stream.Part:
    """Run Basic Pitch on a (typically vocal-isolated) audio file and
    reduce its output to a single melody line as an RH Part."""
    notes = transcribe_audio_to_notes(audio_path)
    melody_notes = reduce_to_monophonic(notes)
    return notes_to_part(melody_notes, part_id="RH")
```

(Add the two new imports to the top of the file alongside the existing
`from app.notation.types import NoteEvent` import.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_melody_extract.py -v`
Expected: PASS (all tests in the file, including the ones from Task 2)

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all tests pass, nothing existing broken (this plan only adds
new files and one new function to `hand_split.py`)

- [ ] **Step 6: Commit**

```bash
git add backend/app/melody/extract.py backend/tests/test_melody_extract.py
git commit -m "feat: add extract_melody_part entry point for melody extraction"
```

## Out of Scope for This Plan

- Wiring `separate_stems` and `extract_melody_part` together (i.e. running
  `extract_melody_part(stems.vocals)`) or into an HTTP endpoint — that's
  Phase 4 (async job infra), which also needs Phase 2's chord recognition
  and Phase 3's arrangement engine (already built) to assemble a full
  grand-staff `Score`.
- Tuning the monophonic-reduction heuristic against real vocal recordings
  — the spec marks this "heuristic TBD... tuned by ear," which needs real
  song material and human judgment, not something to guess further at
  here.
