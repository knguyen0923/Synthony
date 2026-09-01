# Synthony Spec 1: Solo-Piano Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working end-to-end pipeline that takes a solo piano recording (file upload, YouTube link, or Spotify link) and produces three difficulty-tiered MusicXML scores, rendered in a browser via OpenSheetMusicDisplay.

**Architecture:** A FastAPI backend runs a linear pipeline (ingest → Basic Pitch transcription → melody-aware grand-staff notation → pure Easy/Medium/Hard difficulty transforms → MusicXML export), exposed through one synchronous `POST /transcribe` endpoint. A React/Vite frontend submits audio or a link and renders the three resulting scores in tabs.

**Tech Stack:** Python 3.11+, FastAPI, Basic Pitch, music21, librosa, yt-dlp, spotipy, pytest; React 18 + Vite + TypeScript, axios, OpenSheetMusicDisplay, html5-qrcode.

**Spec:** `docs/superpowers/specs/2026-08-31-solo-piano-pipeline-design.md`

## Global Constraints

- Piano only; grand staff, two hands (RH treble / LH bass) — per spec.
- Melody-aware hand split (highest simultaneous note = melody = RH) at every difficulty tier, not a fixed pitch threshold — per spec.
- Difficulty transforms (`easy.py`, `medium.py`, `hard.py`) are pure `Score -> Score` functions with no I/O — per spec.
- `POST /transcribe` is synchronous/blocking — per spec.
- 10-minute audio duration cap, enforced server-side before transcription runs — per spec.
- Spotify input has no legitimate direct-audio path: resolve track metadata via Spotify's official Web API, then match and download via YouTube — per spec. No DRM circumvention.
- All external network calls (yt-dlp, Spotify API) must be mocked in the test suite — no real network calls in tests.
- Fixed-tempo assumption for v1: 120 BPM (0.5 seconds per quarter note). Tempo detection is out of scope; this is a deliberate simplification, not a placeholder.
- No automated frontend test suite for Spec 1 (per spec) — frontend tasks use concrete manual browser-verification steps instead of automated tests.
- `song_id` is a UUID4; storage lives under `backend/storage/{song_id}/` (gitignored, created at runtime).
- Spotify-link input requires `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` environment variables (from a Spotify Developer Dashboard app) to be set before running the backend; without them, Spotify-link requests will fail at the Spotify API auth step. File-upload and YouTube-link input do not require these.

---

## Task 1: Backend Scaffold

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_api.py`
- Create: `.gitignore`

**Interfaces:**
- Produces: `app.main:app` — the FastAPI application instance, extended by later tasks.

- [ ] **Step 1: Create the backend project files**

`backend/requirements.txt`:
```
fastapi
uvicorn[standard]
python-multipart
httpx
basic-pitch
music21
librosa
scipy
numpy
yt-dlp
spotipy
pytest
```

`backend/pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

`.gitignore` (repo root):
```
# Python
__pycache__/
*.pyc
.venv/
backend/storage/

# Node
node_modules/
frontend/dist/

# Editors
.DS_Store
```

`backend/app/__init__.py`: empty file.

- [ ] **Step 2: Set up the virtualenv and install dependencies**

Run:
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
Expected: install completes without errors (Basic Pitch/music21/librosa pull in TensorFlow/scipy transitively — this can take a few minutes).

- [ ] **Step 3: Write the failing test**

`backend/tests/__init__.py`: empty file.

`backend/tests/test_api.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it fails**

Run (from `backend/`, with venv active): `pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'` (file doesn't exist yet).

- [ ] **Step 5: Write minimal implementation**

`backend/app/main.py`:
```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/pyproject.toml backend/app/__init__.py \
  backend/app/main.py backend/tests/__init__.py backend/tests/test_api.py .gitignore
git commit -m "chore: scaffold FastAPI backend with health check"
```

---

## Task 2: Notation — NoteEvent Type + Melody-Aware Hand Split

**Files:**
- Create: `backend/app/notation/__init__.py`
- Create: `backend/app/notation/types.py`
- Create: `backend/app/notation/hand_split.py`
- Test: `backend/tests/test_hand_split.py`

**Interfaces:**
- Produces: `NoteEvent(start: float, end: float, pitch: int, velocity: float = 0.8)` — dataclass; `notes_to_grand_staff(notes: list[NoteEvent]) -> music21.stream.Score` — Score with two `Part`s, `id="RH"` and `id="LH"`; `get_hand_parts(score) -> tuple[Part, Part]` returning `(rh, lh)`.

- [ ] **Step 1: Write the failing tests**

`backend/app/notation/__init__.py`: empty file.

`backend/tests/test_hand_split.py`:
```python
from app.notation.types import NoteEvent
from app.notation.hand_split import notes_to_grand_staff, get_hand_parts


def test_lone_low_note_is_melody_and_goes_to_right_hand():
    notes = [NoteEvent(start=0.0, end=0.5, pitch=48)]  # C3, alone = melody
    score = notes_to_grand_staff(notes)
    rh, lh = get_hand_parts(score)
    assert [n.pitch.midi for n in rh.flatten().notes] == [48]
    assert list(lh.flatten().notes) == []


def test_highest_simultaneous_note_is_melody_rest_are_accompaniment():
    notes = [
        NoteEvent(start=0.0, end=0.5, pitch=60),  # C4 - melody (highest)
        NoteEvent(start=0.0, end=0.5, pitch=48),  # C3 - accompaniment
        NoteEvent(start=0.0, end=0.5, pitch=52),  # E3 - accompaniment
    ]
    score = notes_to_grand_staff(notes)
    rh, lh = get_hand_parts(score)
    assert sorted(n.pitch.midi for n in rh.flatten().notes) == [60]
    assert sorted(n.pitch.midi for n in lh.flatten().notes) == [48, 52]


def test_parts_have_correct_clefs():
    notes = [NoteEvent(start=0.0, end=0.5, pitch=60)]
    score = notes_to_grand_staff(notes)
    rh, lh = get_hand_parts(score)
    assert rh.getElementsByClass("Clef").first().sign == "G"
    assert lh.getElementsByClass("Clef").first().sign == "F"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hand_split.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.notation.types'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/notation/types.py`:
```python
from dataclasses import dataclass


@dataclass(frozen=True)
class NoteEvent:
    start: float       # seconds
    end: float         # seconds
    pitch: int         # MIDI note number, 0-127
    velocity: float = 0.8  # 0.0-1.0
```

`backend/app/notation/hand_split.py`:
```python
from music21 import stream, note, clef

from app.notation.types import NoteEvent

# Fixed-tempo assumption for v1 — tempo detection is out of scope.
SECONDS_PER_QUARTER = 0.5  # 120 BPM


def _seconds_to_quarter_length(seconds: float) -> float:
    return seconds / SECONDS_PER_QUARTER


def _to_music21_note(event: NoteEvent) -> note.Note:
    m21_note = note.Note()
    m21_note.pitch.midi = event.pitch
    duration = _seconds_to_quarter_length(event.end - event.start)
    m21_note.duration.quarterLength = max(duration, 0.25)
    return m21_note


def notes_to_grand_staff(notes: list[NoteEvent]) -> stream.Score:
    """Group notes by onset; the highest-pitched note at each onset is the
    melody and always goes to the right hand, regardless of its absolute
    pitch. Every other simultaneous note goes to the left hand."""
    rh = stream.Part(id="RH")
    rh.append(clef.TrebleClef())
    lh = stream.Part(id="LH")
    lh.append(clef.BassClef())

    by_onset: dict[float, list[NoteEvent]] = {}
    for event in notes:
        by_onset.setdefault(round(event.start, 3), []).append(event)

    for onset in sorted(by_onset):
        group = sorted(by_onset[onset], key=lambda e: e.pitch)
        melody_event = group[-1]
        accompaniment = group[:-1]

        offset = _seconds_to_quarter_length(melody_event.start)
        rh.insert(offset, _to_music21_note(melody_event))
        for event in accompaniment:
            lh.insert(_seconds_to_quarter_length(event.start), _to_music21_note(event))

    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)
    return score


def get_hand_parts(score: stream.Score) -> tuple[stream.Part, stream.Part]:
    rh = next(p for p in score.parts if p.id == "RH")
    lh = next(p for p in score.parts if p.id == "LH")
    return rh, lh
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_hand_split.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/notation/ backend/tests/test_hand_split.py
git commit -m "feat: melody-aware hand split into grand-staff Score"
```

---

## Task 3: Difficulty — Shared Quantize + Range-Shift Helpers

**Files:**
- Create: `backend/app/difficulty/__init__.py`
- Create: `backend/app/difficulty/quantize.py`
- Create: `backend/app/difficulty/range_shift.py`
- Test: `backend/tests/test_quantize.py`
- Test: `backend/tests/test_range_shift.py`

**Interfaces:**
- Consumes: nothing beyond `music21.stream.Part`.
- Produces: `quantize_part(part: Part, grid: float) -> Part` (keeps first note per grid slot, drops the rest); `shift_into_range(part: Part, low: int, high: int) -> Part` (octave-shifts each note's pitch, preserving pitch class, until its MIDI number falls in `[low, high]`).

- [ ] **Step 1: Write the failing tests**

`backend/app/difficulty/__init__.py`: empty file.

`backend/tests/test_quantize.py`:
```python
from music21 import stream, note

from app.difficulty.quantize import quantize_part


def test_keeps_first_note_per_slot_and_drops_the_rest():
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("C4"))
    part.insert(0.1, note.Note("D4"))  # same 1.0-quarterLength grid slot as C4
    part.insert(1.0, note.Note("E4"))

    quantized = quantize_part(part, grid=1.0)

    pitches = [n.pitch.name for n in quantized.flatten().notes]
    assert pitches == ["C", "E"]


def test_quantized_notes_are_snapped_to_the_grid():
    part = stream.Part(id="RH")
    part.insert(0.3, note.Note("C4"))

    quantized = quantize_part(part, grid=1.0)

    offsets = [n.offset for n in quantized.flatten().notes]
    assert offsets == [0.0]
```

`backend/tests/test_range_shift.py`:
```python
from music21 import stream, note

from app.difficulty.range_shift import shift_into_range


def test_note_above_range_is_shifted_down_an_octave():
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("C6"))  # MIDI 84

    shifted = shift_into_range(part, low=60, high=72)  # C4-C5

    pitches = [n.pitch.midi for n in shifted.flatten().notes]
    assert pitches == [72]  # C5, same pitch class, within range


def test_note_below_range_is_shifted_up_an_octave():
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("C2"))  # MIDI 36

    shifted = shift_into_range(part, low=60, high=72)

    pitches = [n.pitch.midi for n in shifted.flatten().notes]
    assert pitches == [60]


def test_note_already_in_range_is_unchanged():
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("E4"))  # MIDI 64

    shifted = shift_into_range(part, low=60, high=72)

    pitches = [n.pitch.midi for n in shifted.flatten().notes]
    assert pitches == [64]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_quantize.py tests/test_range_shift.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.difficulty.quantize'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/difficulty/quantize.py`:
```python
import copy

from music21 import stream


def quantize_part(part: stream.Part, grid: float) -> stream.Part:
    """Snap note onsets to the given grid (in quarterLength units). Keeps
    only the first note whose onset falls in each grid slot; drops the
    rest."""
    quantized = stream.Part(id=part.id)
    seen_slots: set[float] = set()

    for element in part.flatten().notes:
        slot = (element.offset // grid) * grid
        if slot in seen_slots:
            continue
        seen_slots.add(slot)

        new_element = copy.deepcopy(element)
        new_element.duration.quarterLength = grid
        quantized.insert(slot, new_element)

    return quantized
```

`backend/app/difficulty/range_shift.py`:
```python
import copy

from music21 import stream


def shift_into_range(part: stream.Part, low: int, high: int) -> stream.Part:
    """Octave-shift each note's pitch, preserving pitch class, until its
    MIDI number falls within [low, high]."""
    shifted = stream.Part(id=part.id)

    for element in part.flatten().notes:
        new_element = copy.deepcopy(element)
        midi = new_element.pitch.midi
        while midi < low:
            midi += 12
        while midi > high:
            midi -= 12
        new_element.pitch.midi = midi
        shifted.insert(element.offset, new_element)

    return shifted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_quantize.py tests/test_range_shift.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/difficulty/__init__.py backend/app/difficulty/quantize.py \
  backend/app/difficulty/range_shift.py backend/tests/test_quantize.py backend/tests/test_range_shift.py
git commit -m "feat: shared quantize and range-shift helpers for difficulty engine"
```

---

## Task 4: Difficulty — Easy Transform

**Files:**
- Create: `backend/app/difficulty/easy.py`
- Test: `backend/tests/test_easy.py`

**Interfaces:**
- Consumes: `get_hand_parts` from `app.notation.hand_split`; `quantize_part`, `shift_into_range` from Task 3.
- Produces: `to_easy(score: music21.stream.Score) -> music21.stream.Score` — two-part Score (`RH`, `LH`), quarter-note-quantized melody, root-note-only bass, both hands range-narrowed to one octave.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_easy.py`:
```python
from music21 import stream, note

from app.notation.hand_split import get_hand_parts
from app.difficulty.easy import to_easy


def _score(rh_notes: list[tuple[float, str]], lh_notes: list[tuple[float, str]]) -> stream.Score:
    rh = stream.Part(id="RH")
    for offset, pitch_name in rh_notes:
        rh.insert(offset, note.Note(pitch_name))
    lh = stream.Part(id="LH")
    for offset, pitch_name in lh_notes:
        lh.insert(offset, note.Note(pitch_name))
    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)
    return score


def test_easy_melody_is_quarter_quantized_and_range_narrowed():
    score = _score(
        rh_notes=[(0.0, "C6"), (0.1, "D6")],  # same grid slot; C6 out of range
        lh_notes=[],
    )
    easy_score = to_easy(score)
    rh, _ = get_hand_parts(easy_score)
    notes = list(rh.flatten().notes)
    assert len(notes) == 1
    assert notes[0].pitch.midi == 72  # C6 (MIDI 96) octave-shifted down to C5


def test_easy_bass_reduces_to_lowest_note_per_slot():
    score = _score(
        rh_notes=[],
        lh_notes=[(0.0, "C3"), (0.0, "E3"), (0.0, "G3")],
    )
    easy_score = to_easy(score)
    _, lh = get_hand_parts(easy_score)
    notes = list(lh.flatten().notes)
    assert len(notes) == 1
    assert notes[0].pitch.name == "C"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_easy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.difficulty.easy'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/difficulty/easy.py`:
```python
import copy

from music21 import stream

from app.notation.hand_split import get_hand_parts
from app.difficulty.quantize import quantize_part
from app.difficulty.range_shift import shift_into_range

EASY_GRID = 1.0            # quarter note
EASY_RH_RANGE = (60, 72)   # one octave, C4-C5
EASY_LH_RANGE = (36, 48)   # one octave, C2-C3


def to_easy(score: stream.Score) -> stream.Score:
    rh, lh = get_hand_parts(score)

    rh_quantized = quantize_part(rh, EASY_GRID)
    lh_root = _reduce_to_root_per_slot(lh, EASY_GRID)

    rh_ranged = shift_into_range(rh_quantized, *EASY_RH_RANGE)
    lh_ranged = shift_into_range(lh_root, *EASY_LH_RANGE)

    for part in (rh_ranged, lh_ranged):
        for element in part.flatten().notes:
            element.pitch.simplifyEnharmonic(inPlace=True)

    easy_score = stream.Score()
    easy_score.insert(0, rh_ranged)
    easy_score.insert(0, lh_ranged)
    return easy_score


def _reduce_to_root_per_slot(lh_part: stream.Part, grid: float) -> stream.Part:
    """Keep only the lowest-pitched note in each grid slot, as the root
    bass note."""
    by_slot: dict[float, list] = {}
    for element in lh_part.flatten().notes:
        slot = (element.offset // grid) * grid
        by_slot.setdefault(slot, []).append(element)

    reduced = stream.Part(id=lh_part.id)
    for slot in sorted(by_slot):
        lowest = min(by_slot[slot], key=lambda n: n.pitch.midi)
        new_element = copy.deepcopy(lowest)
        new_element.duration.quarterLength = grid
        reduced.insert(slot, new_element)
    return reduced
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_easy.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/difficulty/easy.py backend/tests/test_easy.py
git commit -m "feat: Easy difficulty transform"
```

---

## Task 5: Difficulty — Medium Transform

**Files:**
- Create: `backend/app/difficulty/medium.py`
- Test: `backend/tests/test_medium.py`

**Interfaces:**
- Consumes: `get_hand_parts` from `app.notation.hand_split`; `quantize_part`, `shift_into_range` from Task 3.
- Produces: `to_medium(score: music21.stream.Score) -> music21.stream.Score` — two-part Score, eighth-note-quantized melody, LH voiced to up to 3 distinct-pitch-class tones per slot, both hands range-narrowed wider than Easy.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_medium.py`:
```python
from music21 import stream, note

from app.notation.hand_split import get_hand_parts
from app.difficulty.medium import to_medium


def _score(rh_notes: list[tuple[float, str]], lh_notes: list[tuple[float, str]]) -> stream.Score:
    rh = stream.Part(id="RH")
    for offset, pitch_name in rh_notes:
        rh.insert(offset, note.Note(pitch_name))
    lh = stream.Part(id="LH")
    for offset, pitch_name in lh_notes:
        lh.insert(offset, note.Note(pitch_name))
    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)
    return score


def test_medium_melody_quantizes_to_eighth_grid():
    score = _score(
        rh_notes=[(0.0, "C4"), (0.4, "D4"), (0.5, "E4")],
        lh_notes=[],
    )
    medium_score = to_medium(score)
    rh, _ = get_hand_parts(medium_score)
    offsets = sorted(n.offset for n in rh.flatten().notes)
    # grid = 0.5: slot 0 keeps first note (C4 at 0.0), slot 0.5 keeps E4
    assert offsets == [0.0, 0.5]


def test_medium_bass_voices_up_to_three_distinct_pitch_classes():
    score = _score(
        rh_notes=[],
        lh_notes=[(0.0, "C3"), (0.0, "C4"), (0.0, "E3"), (0.0, "G3"), (0.0, "B3")],
    )
    medium_score = to_medium(score)
    _, lh = get_hand_parts(medium_score)
    notes = sorted(lh.flatten().notes, key=lambda n: n.pitch.midi)
    pitch_names = [n.pitch.name for n in notes]
    assert len(notes) == 3               # capped at 3 tones
    assert pitch_names == ["C", "E", "G"]  # doubled C4 dropped; B3 excluded (4th tone)
    assert notes[0].pitch.midi == 48      # lowest C instance kept (C3, not C4)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_medium.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.difficulty.medium'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/difficulty/medium.py`:
```python
import copy

from music21 import stream

from app.notation.hand_split import get_hand_parts
from app.difficulty.quantize import quantize_part
from app.difficulty.range_shift import shift_into_range

MEDIUM_GRID = 0.5          # eighth note
MEDIUM_RH_RANGE = (55, 79) # roughly two octaves, G3-G5
MEDIUM_LH_RANGE = (36, 55) # C2-G3
MAX_VOICING_TONES = 3


def to_medium(score: stream.Score) -> stream.Score:
    rh, lh = get_hand_parts(score)

    rh_quantized = quantize_part(rh, MEDIUM_GRID)
    lh_voiced = _voice_chords_per_slot(lh, MEDIUM_GRID)

    rh_ranged = shift_into_range(rh_quantized, *MEDIUM_RH_RANGE)
    lh_ranged = shift_into_range(lh_voiced, *MEDIUM_LH_RANGE)

    medium_score = stream.Score()
    medium_score.insert(0, rh_ranged)
    medium_score.insert(0, lh_ranged)
    return medium_score


def _voice_chords_per_slot(lh_part: stream.Part, grid: float) -> stream.Part:
    by_slot: dict[float, list] = {}
    for element in lh_part.flatten().notes:
        slot = (element.offset // grid) * grid
        by_slot.setdefault(slot, []).append(element)

    voiced = stream.Part(id=lh_part.id)
    for slot in sorted(by_slot):
        for tone in _reduce_to_voicing(by_slot[slot]):
            new_element = copy.deepcopy(tone)
            new_element.duration.quarterLength = grid
            voiced.insert(slot, new_element)
    return voiced


def _reduce_to_voicing(notes: list) -> list:
    """Drop doubled pitch classes (keeping the lowest instance of each),
    then cap at MAX_VOICING_TONES tones, lowest first."""
    by_pitch_class: dict[int, object] = {}
    for n in notes:
        pitch_class = n.pitch.pitchClass
        existing = by_pitch_class.get(pitch_class)
        if existing is None or n.pitch.midi < existing.pitch.midi:
            by_pitch_class[pitch_class] = n

    ordered = sorted(by_pitch_class.values(), key=lambda n: n.pitch.midi)
    return ordered[:MAX_VOICING_TONES]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_medium.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/difficulty/medium.py backend/tests/test_medium.py
git commit -m "feat: Medium difficulty transform"
```

---

## Task 6: Difficulty — Hard Transform

**Files:**
- Create: `backend/app/difficulty/hard.py`
- Test: `backend/tests/test_hard.py`

**Interfaces:**
- Produces: `to_hard(score: music21.stream.Score) -> music21.stream.Score` — deep-copy passthrough (no simplification).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_hard.py`:
```python
from music21 import stream, note

from app.notation.hand_split import get_hand_parts
from app.difficulty.hard import to_hard


def test_hard_is_an_unmodified_deep_copy():
    rh = stream.Part(id="RH")
    rh.insert(0.0, note.Note("C6"))  # deliberately out of any "range" window
    lh = stream.Part(id="LH")
    lh.insert(0.0, note.Note("C2"))
    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)

    hard_score = to_hard(score)

    hard_rh, hard_lh = get_hand_parts(hard_score)
    assert [n.pitch.midi for n in hard_rh.flatten().notes] == [96]  # unchanged
    assert [n.pitch.midi for n in hard_lh.flatten().notes] == [36]  # unchanged
    assert hard_score is not score  # independent copy, not the same object
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.difficulty.hard'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/difficulty/hard.py`:
```python
import copy

from music21 import stream


def to_hard(score: stream.Score) -> stream.Score:
    """Passthrough — Hard tier is the melody-split, grand-staff score as
    is, with no simplification."""
    return copy.deepcopy(score)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hard.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/difficulty/hard.py backend/tests/test_hard.py
git commit -m "feat: Hard difficulty transform (passthrough)"
```

---

## Task 7: Difficulty — Engine Orchestrator

**Files:**
- Create: `backend/app/difficulty/engine.py`
- Test: `backend/tests/test_engine.py`

**Interfaces:**
- Consumes: `to_easy`, `to_medium`, `to_hard`, `get_hand_parts`.
- Produces: `DifficultyVariants(easy, medium, hard)` dataclass of `music21.stream.Score`; `generate_variants(score: music21.stream.Score) -> DifficultyVariants`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_engine.py`:
```python
from music21 import stream, note

from app.notation.hand_split import get_hand_parts
from app.difficulty.engine import generate_variants


def test_generate_variants_returns_all_three_tiers_with_correct_hand_ids():
    rh = stream.Part(id="RH")
    rh.insert(0.0, note.Note("C4"))
    rh.insert(0.5, note.Note("D4"))
    lh = stream.Part(id="LH")
    lh.insert(0.0, note.Note("C3"))
    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)

    variants = generate_variants(score)

    for variant_score in (variants.easy, variants.medium, variants.hard):
        variant_rh, variant_lh = get_hand_parts(variant_score)
        assert variant_rh.id == "RH"
        assert variant_lh.id == "LH"

    # Easy quantizes to a coarser grid than Hard, so it should never have
    # more notes than Hard for the same input.
    easy_rh, _ = get_hand_parts(variants.easy)
    hard_rh, _ = get_hand_parts(variants.hard)
    assert len(list(easy_rh.flatten().notes)) <= len(list(hard_rh.flatten().notes))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.difficulty.engine'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/difficulty/engine.py`:
```python
from dataclasses import dataclass

from music21 import stream

from app.difficulty.easy import to_easy
from app.difficulty.medium import to_medium
from app.difficulty.hard import to_hard


@dataclass
class DifficultyVariants:
    easy: stream.Score
    medium: stream.Score
    hard: stream.Score


def generate_variants(score: stream.Score) -> DifficultyVariants:
    return DifficultyVariants(
        easy=to_easy(score),
        medium=to_medium(score),
        hard=to_hard(score),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/difficulty/engine.py backend/tests/test_engine.py
git commit -m "feat: difficulty engine orchestrator"
```

---

## Task 8: Transcription — Basic Pitch Wrapper

**Files:**
- Create: `backend/app/transcription/__init__.py`
- Create: `backend/app/transcription/audio_to_midi.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_audio_to_midi.py`

**Interfaces:**
- Produces: `transcribe_audio_to_notes(audio_path: str) -> list[NoteEvent]`.
- Produces (shared test fixture): `synthetic_piano_wav` pytest fixture — a 2-second synthetic A4 (440Hz) tone WAV, usable by any later test needing real audio input.

- [ ] **Step 1: Write the failing test and shared fixture**

`backend/app/transcription/__init__.py`: empty file.

`backend/tests/conftest.py`:
```python
import shutil

import numpy as np
import pytest
from scipy.io import wavfile

from app.storage import STORAGE_ROOT


@pytest.fixture
def synthetic_piano_wav(tmp_path):
    """A short synthetic WAV: a single held A4 (440Hz) tone, 2 seconds."""
    sample_rate = 22050
    duration_s = 2.0
    frequency_hz = 440.0

    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    tone = 0.5 * np.sin(2 * np.pi * frequency_hz * t)
    audio = (tone * 32767).astype(np.int16)

    wav_path = tmp_path / "synthetic_piano.wav"
    wavfile.write(str(wav_path), sample_rate, audio)
    return wav_path


@pytest.fixture(autouse=True)
def clean_storage():
    yield
    if STORAGE_ROOT.exists():
        shutil.rmtree(STORAGE_ROOT)
```

`backend/tests/test_audio_to_midi.py`:
```python
from app.transcription.audio_to_midi import transcribe_audio_to_notes


def test_transcribe_detects_note_near_a4(synthetic_piano_wav):
    notes = transcribe_audio_to_notes(str(synthetic_piano_wav))

    assert len(notes) >= 1
    pitches = [n.pitch for n in notes]
    assert any(abs(p - 69) <= 2 for p in pitches)  # A4 = MIDI 69, +/-2 semitone tolerance
```

Note: this test imports `app.storage`, which does not exist until Task 10. Skip running `conftest.py`'s `clean_storage` fixture for now by proceeding directly to Task 10 if this import fails — but since Task 10 comes after this one in the plan, temporarily stub it out:

- [ ] **Step 1b: Add a placeholder storage module so conftest.py can import it**

`backend/app/storage.py` (minimal placeholder; Task 10 will expand this file):
```python
from pathlib import Path

STORAGE_ROOT = Path(__file__).resolve().parent.parent / "storage"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audio_to_midi.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.transcription.audio_to_midi'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/transcription/audio_to_midi.py`:
```python
from basic_pitch import ICASSP_2022_MODEL_PATH
from basic_pitch.inference import predict

from app.notation.types import NoteEvent


def transcribe_audio_to_notes(audio_path: str) -> list[NoteEvent]:
    _, _, note_events = predict(audio_path, ICASSP_2022_MODEL_PATH)
    return [
        NoteEvent(
            start=start,
            end=end,
            pitch=pitch,
            velocity=min(max(amplitude, 0.0), 1.0),
        )
        for start, end, pitch, amplitude, _pitch_bend in note_events
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audio_to_midi.py -v`
Expected: PASS. (This runs a real Basic Pitch model inference and may take several seconds the first time as the model loads.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/transcription/ backend/app/storage.py backend/tests/conftest.py backend/tests/test_audio_to_midi.py
git commit -m "feat: Basic Pitch audio-to-notes transcription wrapper"
```

---

## Task 9: MusicXML Export

**Files:**
- Create: `backend/app/export.py`
- Test: `backend/tests/test_export.py`

**Interfaces:**
- Produces: `export_musicxml(score: music21.stream.Score, output_path: pathlib.Path) -> pathlib.Path`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_export.py`:
```python
from music21 import stream, note

from app.export import export_musicxml


def test_export_writes_a_musicxml_file(tmp_path):
    score = stream.Score()
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("C4"))
    score.insert(0, part)

    output_path = tmp_path / "nested" / "easy.musicxml"
    result = export_musicxml(score, output_path)

    assert result == output_path
    assert output_path.exists()
    assert "<score-partwise" in output_path.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.export'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/export.py`:
```python
from pathlib import Path

from music21 import stream


def export_musicxml(score: stream.Score, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    score.write("musicxml", fp=str(output_path))
    return output_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_export.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/export.py backend/tests/test_export.py
git commit -m "feat: MusicXML export helper"
```

---

## Task 10: Storage — Song ID, Directory, and Metadata Helpers

**Files:**
- Modify: `backend/app/storage.py` (replace the Task 8 placeholder with the full module)
- Test: `backend/tests/test_storage.py`

**Interfaces:**
- Produces: `STORAGE_ROOT: pathlib.Path`; `new_song_id() -> str`; `song_dir(song_id: str) -> pathlib.Path` (creates the directory); `write_metadata(song_id: str, title: str, source_type: str, source_url: str | None) -> None`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_storage.py`:
```python
import json
import uuid

from app.storage import new_song_id, song_dir, write_metadata, STORAGE_ROOT


def test_new_song_id_is_a_valid_uuid4():
    song_id = new_song_id()
    assert uuid.UUID(song_id).version == 4


def test_song_dir_creates_and_returns_the_directory():
    song_id = new_song_id()
    path = song_dir(song_id)
    assert path == STORAGE_ROOT / song_id
    assert path.is_dir()


def test_write_metadata_writes_expected_json_fields():
    song_id = new_song_id()
    song_dir(song_id)

    write_metadata(song_id, title="My Song", source_type="upload", source_url=None)

    metadata_path = STORAGE_ROOT / song_id / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    assert metadata["title"] == "My Song"
    assert metadata["source_type"] == "upload"
    assert metadata["source_url"] is None
    assert "created_at" in metadata
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL — `ImportError: cannot import name 'new_song_id' from 'app.storage'`

- [ ] **Step 3: Write the full implementation**

`backend/app/storage.py` (replaces the Task 8 placeholder):
```python
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

STORAGE_ROOT = Path(__file__).resolve().parent.parent / "storage"


def new_song_id() -> str:
    return str(uuid.uuid4())


def song_dir(song_id: str) -> Path:
    path = STORAGE_ROOT / song_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_metadata(song_id: str, title: str, source_type: str, source_url: str | None) -> None:
    metadata = {
        "title": title,
        "source_type": source_type,
        "source_url": source_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (song_dir(song_id) / "metadata.json").write_text(json.dumps(metadata, indent=2))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_storage.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage.py backend/tests/test_storage.py
git commit -m "feat: song storage — id generation, directories, metadata"
```

---

## Task 11: Ingestion — File Upload Normalization

**Files:**
- Create: `backend/app/ingestion/__init__.py`
- Create: `backend/app/ingestion/upload.py`
- Test: `backend/tests/test_upload.py`

**Interfaces:**
- Produces: `UnsupportedAudioFormat(Exception)`; `save_uploaded_file(source_path: Path, dest_dir: Path, original_filename: str) -> Path`.

- [ ] **Step 1: Write the failing tests**

`backend/app/ingestion/__init__.py`: empty file.

`backend/tests/test_upload.py`:
```python
import pytest

from app.ingestion.upload import save_uploaded_file, UnsupportedAudioFormat


def test_save_uploaded_file_copies_wav_to_dest_dir(tmp_path):
    source = tmp_path / "input.wav"
    source.write_bytes(b"fake wav bytes")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    result = save_uploaded_file(source, dest_dir, "input.wav")

    assert result == dest_dir / "source.wav"
    assert result.read_bytes() == b"fake wav bytes"


def test_save_uploaded_file_rejects_unsupported_extension(tmp_path):
    source = tmp_path / "input.flac"
    source.write_bytes(b"fake flac bytes")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    with pytest.raises(UnsupportedAudioFormat):
        save_uploaded_file(source, dest_dir, "input.flac")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_upload.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingestion.upload'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/ingestion/upload.py`:
```python
import shutil
from pathlib import Path

SUPPORTED_EXTENSIONS = {".wav", ".mp3"}


class UnsupportedAudioFormat(Exception):
    pass


def save_uploaded_file(source_path: Path, dest_dir: Path, original_filename: str) -> Path:
    ext = Path(original_filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedAudioFormat(f"Unsupported file type: {ext}")

    dest_path = dest_dir / f"source{ext}"
    shutil.copy(source_path, dest_path)
    return dest_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_upload.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/__init__.py backend/app/ingestion/upload.py backend/tests/test_upload.py
git commit -m "feat: file-upload ingestion"
```

---

## Task 12: Ingestion — YouTube Download

**Files:**
- Create: `backend/app/ingestion/youtube.py`
- Test: `backend/tests/test_youtube.py`

**Interfaces:**
- Produces: `YouTubeResolutionError(Exception)`; `download_audio(url: str, dest_dir: Path) -> Path` (returns `dest_dir / "source.mp3"`).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_youtube.py`:
```python
import pytest
import yt_dlp

from app.ingestion.youtube import download_audio, YouTubeResolutionError


class _FakeYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def download(self, urls):
        self.downloaded_urls = urls


def test_download_audio_calls_yt_dlp_and_returns_expected_path(tmp_path, monkeypatch):
    captured = {}

    def fake_youtube_dl(options):
        captured["options"] = options
        return _FakeYoutubeDL(options)

    monkeypatch.setattr(yt_dlp, "YoutubeDL", fake_youtube_dl)

    result = download_audio("https://youtube.com/watch?v=abc123", tmp_path)

    assert result == tmp_path / "source.mp3"
    assert captured["options"]["outtmpl"] == str(tmp_path / "source.%(ext)s")


def test_download_audio_wraps_download_errors(tmp_path, monkeypatch):
    class _FailingYoutubeDL(_FakeYoutubeDL):
        def download(self, urls):
            raise yt_dlp.utils.DownloadError("video unavailable")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", lambda options: _FailingYoutubeDL(options))

    with pytest.raises(YouTubeResolutionError):
        download_audio("https://youtube.com/watch?v=broken", tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_youtube.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingestion.youtube'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/ingestion/youtube.py`:
```python
from pathlib import Path

import yt_dlp


class YouTubeResolutionError(Exception):
    pass


def download_audio(url: str, dest_dir: Path) -> Path:
    options = {
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
        }],
        "quiet": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        raise YouTubeResolutionError(f"Could not download audio from {url}") from exc

    return dest_dir / "source.mp3"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_youtube.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/youtube.py backend/tests/test_youtube.py
git commit -m "feat: YouTube audio download ingestion"
```

---

## Task 13: Ingestion — Spotify Resolution via YouTube Search

**Files:**
- Create: `backend/app/ingestion/spotify.py`
- Test: `backend/tests/test_spotify.py`

**Interfaces:**
- Consumes: `download_audio`, `YouTubeResolutionError` from Task 12.
- Produces: `SpotifyResolutionError(Exception)`; `resolve_and_download(spotify_url: str, dest_dir: Path, client_id: str, client_secret: str) -> Path`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_spotify.py`:
```python
import pytest
import spotipy

from app.ingestion import spotify as spotify_module
from app.ingestion.spotify import resolve_and_download, SpotifyResolutionError
from app.ingestion.youtube import YouTubeResolutionError


class _FakeSpotifyClient:
    def __init__(self, *, track_data=None, raise_error=False):
        self._track_data = track_data
        self._raise_error = raise_error

    def track(self, track_id):
        if self._raise_error:
            raise spotipy.SpotifyException(404, -1, "not found")
        return self._track_data


def test_resolve_and_download_happy_path(tmp_path, monkeypatch):
    fake_track = {"name": "Clair de Lune", "artists": [{"name": "Debussy"}]}
    monkeypatch.setattr(spotify_module, "SpotifyClientCredentials", lambda **kwargs: None)
    monkeypatch.setattr(
        spotify_module.spotipy, "Spotify",
        lambda auth_manager: _FakeSpotifyClient(track_data=fake_track),
    )
    monkeypatch.setattr(spotify_module, "_search_youtube", lambda query: "https://youtube.com/watch?v=xyz")
    monkeypatch.setattr(
        spotify_module, "download_audio",
        lambda url, dest_dir: dest_dir / "source.mp3",
    )

    result = resolve_and_download(
        "https://open.spotify.com/track/abc123", tmp_path, "id", "secret"
    )

    assert result == tmp_path / "source.mp3"


def test_resolve_and_download_raises_on_unparseable_url(tmp_path):
    with pytest.raises(SpotifyResolutionError):
        resolve_and_download("https://open.spotify.com/album/notatrack", tmp_path, "id", "secret")


def test_resolve_and_download_raises_when_no_youtube_match(tmp_path, monkeypatch):
    fake_track = {"name": "Obscure Track", "artists": [{"name": "Nobody"}]}
    monkeypatch.setattr(spotify_module, "SpotifyClientCredentials", lambda **kwargs: None)
    monkeypatch.setattr(
        spotify_module.spotipy, "Spotify",
        lambda auth_manager: _FakeSpotifyClient(track_data=fake_track),
    )
    monkeypatch.setattr(spotify_module, "_search_youtube", lambda query: None)

    with pytest.raises(SpotifyResolutionError):
        resolve_and_download(
            "https://open.spotify.com/track/abc123", tmp_path, "id", "secret"
        )


def test_resolve_and_download_wraps_youtube_download_failure(tmp_path, monkeypatch):
    fake_track = {"name": "Clair de Lune", "artists": [{"name": "Debussy"}]}
    monkeypatch.setattr(spotify_module, "SpotifyClientCredentials", lambda **kwargs: None)
    monkeypatch.setattr(
        spotify_module.spotipy, "Spotify",
        lambda auth_manager: _FakeSpotifyClient(track_data=fake_track),
    )
    monkeypatch.setattr(spotify_module, "_search_youtube", lambda query: "https://youtube.com/watch?v=xyz")

    def failing_download(url, dest_dir):
        raise YouTubeResolutionError("download failed")

    monkeypatch.setattr(spotify_module, "download_audio", failing_download)

    with pytest.raises(SpotifyResolutionError):
        resolve_and_download(
            "https://open.spotify.com/track/abc123", tmp_path, "id", "secret"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_spotify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingestion.spotify'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/ingestion/spotify.py`:
```python
import re
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from app.ingestion.youtube import download_audio, YouTubeResolutionError

TRACK_ID_PATTERN = re.compile(r"track/([a-zA-Z0-9]+)")


class SpotifyResolutionError(Exception):
    pass


def resolve_and_download(spotify_url: str, dest_dir: Path, client_id: str, client_secret: str) -> Path:
    match = TRACK_ID_PATTERN.search(spotify_url)
    if not match:
        raise SpotifyResolutionError(f"Could not parse Spotify track URL: {spotify_url}")
    track_id = match.group(1)

    auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    client = spotipy.Spotify(auth_manager=auth_manager)
    try:
        track = client.track(track_id)
    except spotipy.SpotifyException as exc:
        raise SpotifyResolutionError(f"Could not resolve Spotify track: {spotify_url}") from exc

    title = track["name"]
    artist = track["artists"][0]["name"]
    search_query = f"{title} {artist}"

    youtube_url = _search_youtube(search_query)
    if youtube_url is None:
        raise SpotifyResolutionError(f"No YouTube match found for '{search_query}'")

    try:
        return download_audio(youtube_url, dest_dir)
    except YouTubeResolutionError as exc:
        raise SpotifyResolutionError(str(exc)) from exc


def _search_youtube(query: str) -> str | None:
    import yt_dlp

    options = {"quiet": True, "default_search": "ytsearch1", "noplaylist": True}
    with yt_dlp.YoutubeDL(options) as ydl:
        result = ydl.extract_info(query, download=False)
        entries = result.get("entries") or []
        if not entries:
            return None
        return entries[0]["webpage_url"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_spotify.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/spotify.py backend/tests/test_spotify.py
git commit -m "feat: Spotify-to-YouTube ingestion resolution"
```

---

## Task 14: Ingestion — Normalize Dispatcher

**Files:**
- Create: `backend/app/ingestion/normalize.py`
- Test: `backend/tests/test_normalize.py`

**Interfaces:**
- Consumes: `save_uploaded_file`, `UnsupportedAudioFormat` (Task 11); `download_audio`, `YouTubeResolutionError` (Task 12); `resolve_and_download`, `SpotifyResolutionError` (Task 13).
- Produces: `IngestionError(Exception)` with `.status_code: int`; `IngestedAudio(path: Path, source_type: str, source_url: str | None)` dataclass; `ingest(dest_dir, *, uploaded_file_path=None, uploaded_filename=None, youtube_url=None, spotify_url=None, spotify_client_id="", spotify_client_secret="") -> IngestedAudio`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_normalize.py`:
```python
import pytest

from app.ingestion import normalize as normalize_module
from app.ingestion.normalize import ingest, IngestionError
from app.ingestion.upload import UnsupportedAudioFormat
from app.ingestion.youtube import YouTubeResolutionError
from app.ingestion.spotify import SpotifyResolutionError


def test_ingest_dispatches_to_file_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(
        normalize_module, "save_uploaded_file",
        lambda source, dest_dir, filename: dest_dir / "source.wav",
    )

    result = ingest(tmp_path, uploaded_file_path=tmp_path / "in.wav", uploaded_filename="in.wav")

    assert result.source_type == "upload"
    assert result.source_url is None
    assert result.path == tmp_path / "source.wav"


def test_ingest_dispatches_to_youtube(tmp_path, monkeypatch):
    monkeypatch.setattr(
        normalize_module, "download_audio",
        lambda url, dest_dir: dest_dir / "source.mp3",
    )

    result = ingest(tmp_path, youtube_url="https://youtube.com/watch?v=abc")

    assert result.source_type == "youtube"
    assert result.source_url == "https://youtube.com/watch?v=abc"


def test_ingest_dispatches_to_spotify(tmp_path, monkeypatch):
    monkeypatch.setattr(
        normalize_module, "resolve_and_download",
        lambda url, dest_dir, client_id, client_secret: dest_dir / "source.mp3",
    )

    result = ingest(tmp_path, spotify_url="https://open.spotify.com/track/abc")

    assert result.source_type == "spotify"


def test_ingest_raises_400_when_no_input_provided(tmp_path):
    with pytest.raises(IngestionError) as exc_info:
        ingest(tmp_path)
    assert exc_info.value.status_code == 400


def test_ingest_wraps_unsupported_format_as_400(tmp_path, monkeypatch):
    def raise_unsupported(source, dest_dir, filename):
        raise UnsupportedAudioFormat("bad format")

    monkeypatch.setattr(normalize_module, "save_uploaded_file", raise_unsupported)

    with pytest.raises(IngestionError) as exc_info:
        ingest(tmp_path, uploaded_file_path=tmp_path / "in.flac", uploaded_filename="in.flac")
    assert exc_info.value.status_code == 400


def test_ingest_wraps_youtube_failure_as_422(tmp_path, monkeypatch):
    def raise_youtube_error(url, dest_dir):
        raise YouTubeResolutionError("unavailable")

    monkeypatch.setattr(normalize_module, "download_audio", raise_youtube_error)

    with pytest.raises(IngestionError) as exc_info:
        ingest(tmp_path, youtube_url="https://youtube.com/watch?v=broken")
    assert exc_info.value.status_code == 422


def test_ingest_wraps_spotify_failure_as_422(tmp_path, monkeypatch):
    def raise_spotify_error(url, dest_dir, client_id, client_secret):
        raise SpotifyResolutionError("no match")

    monkeypatch.setattr(normalize_module, "resolve_and_download", raise_spotify_error)

    with pytest.raises(IngestionError) as exc_info:
        ingest(tmp_path, spotify_url="https://open.spotify.com/track/abc")
    assert exc_info.value.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ingestion.normalize'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/ingestion/normalize.py`:
```python
from dataclasses import dataclass
from pathlib import Path

from app.ingestion.upload import save_uploaded_file, UnsupportedAudioFormat
from app.ingestion.youtube import download_audio, YouTubeResolutionError
from app.ingestion.spotify import resolve_and_download, SpotifyResolutionError


class IngestionError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class IngestedAudio:
    path: Path
    source_type: str
    source_url: str | None


def ingest(
    dest_dir: Path,
    *,
    uploaded_file_path: Path | None = None,
    uploaded_filename: str | None = None,
    youtube_url: str | None = None,
    spotify_url: str | None = None,
    spotify_client_id: str = "",
    spotify_client_secret: str = "",
) -> IngestedAudio:
    if uploaded_file_path is not None:
        try:
            path = save_uploaded_file(uploaded_file_path, dest_dir, uploaded_filename or "")
        except UnsupportedAudioFormat as exc:
            raise IngestionError(str(exc), 400) from exc
        return IngestedAudio(path=path, source_type="upload", source_url=None)

    if youtube_url is not None:
        try:
            path = download_audio(youtube_url, dest_dir)
        except YouTubeResolutionError as exc:
            raise IngestionError(str(exc), 422) from exc
        return IngestedAudio(path=path, source_type="youtube", source_url=youtube_url)

    if spotify_url is not None:
        try:
            path = resolve_and_download(
                spotify_url, dest_dir, spotify_client_id, spotify_client_secret
            )
        except SpotifyResolutionError as exc:
            raise IngestionError(str(exc), 422) from exc
        return IngestedAudio(path=path, source_type="spotify", source_url=spotify_url)

    raise IngestionError("No input source provided", 400)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_normalize.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/normalize.py backend/tests/test_normalize.py
git commit -m "feat: unified ingestion dispatcher (upload/YouTube/Spotify)"
```

---

## Task 15: API — POST /transcribe End-to-End Wiring

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api.py` (extend)

**Interfaces:**
- Consumes: `ingest`, `IngestionError` (Task 14); `transcribe_audio_to_notes` (Task 8); `notes_to_grand_staff` (Task 2); `generate_variants` (Task 7); `export_musicxml` (Task 9); `new_song_id`, `song_dir`, `write_metadata`, `STORAGE_ROOT` (Task 10).
- Produces: `POST /transcribe` route; static file serving of `backend/storage/` at `/storage`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_api.py`:
```python
from pathlib import Path

from app.storage import STORAGE_ROOT


def test_transcribe_with_file_upload_returns_all_three_difficulties(synthetic_piano_wav):
    with open(synthetic_piano_wav, "rb") as f:
        response = client.post(
            "/transcribe",
            files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
        )

    assert response.status_code == 200
    body = response.json()
    assert set(body["difficulties"].keys()) == {"easy", "medium", "hard"}

    song_id = body["song_id"]
    for tier in ("easy", "medium", "hard"):
        musicxml_path = STORAGE_ROOT / song_id / f"{tier}.musicxml"
        assert musicxml_path.exists()


def test_transcribe_with_no_input_returns_400():
    response = client.post("/transcribe")
    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -v`
Expected: FAIL — `404 Not Found` for `/transcribe` (route doesn't exist yet).

- [ ] **Step 3: Write the full implementation**

`backend/app/main.py`:
```python
import os
import tempfile
from pathlib import Path
from typing import Optional

import librosa
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.ingestion.normalize import ingest, IngestionError
from app.transcription.audio_to_midi import transcribe_audio_to_notes
from app.notation.hand_split import notes_to_grand_staff
from app.difficulty.engine import generate_variants
from app.export import export_musicxml
from app.storage import new_song_id, song_dir, write_metadata, STORAGE_ROOT

MAX_DURATION_SECONDS = 600  # 10 minutes

# Required only for Spotify-link input (resolved via Spotify's Web API,
# then matched and downloaded through YouTube — see ingestion/spotify.py).
# Create an app at https://developer.spotify.com/dashboard to obtain these.
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")

STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.mount("/storage", StaticFiles(directory=str(STORAGE_ROOT)), name="storage")


class DifficultyLink(BaseModel):
    musicxml_url: str


class TranscribeResponse(BaseModel):
    song_id: str
    title: str
    difficulties: dict[str, DifficultyLink]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio_file: Optional[UploadFile] = File(None),
    youtube_url: Optional[str] = Form(None),
    spotify_url: Optional[str] = Form(None),
) -> TranscribeResponse:
    song_id = new_song_id()
    dest_dir = song_dir(song_id)

    with tempfile.TemporaryDirectory() as tmp:
        upload_tmp_path = None
        upload_filename = None
        if audio_file is not None:
            upload_tmp_path = Path(tmp) / audio_file.filename
            upload_tmp_path.write_bytes(await audio_file.read())
            upload_filename = audio_file.filename

        try:
            ingested = ingest(
                dest_dir,
                uploaded_file_path=upload_tmp_path,
                uploaded_filename=upload_filename,
                youtube_url=youtube_url,
                spotify_url=spotify_url,
                spotify_client_id=SPOTIFY_CLIENT_ID,
                spotify_client_secret=SPOTIFY_CLIENT_SECRET,
            )
        except IngestionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    duration = librosa.get_duration(path=str(ingested.path))
    if duration > MAX_DURATION_SECONDS:
        raise HTTPException(status_code=413, detail="Audio exceeds the 10-minute duration cap")

    notes = transcribe_audio_to_notes(str(ingested.path))
    if not notes:
        raise HTTPException(status_code=422, detail="No pitched content detected")

    score = notes_to_grand_staff(notes)
    variants = generate_variants(score)

    for tier, variant_score in (
        ("easy", variants.easy),
        ("medium", variants.medium),
        ("hard", variants.hard),
    ):
        export_musicxml(variant_score, dest_dir / f"{tier}.musicxml")

    title = Path(ingested.path).stem
    write_metadata(song_id, title=title, source_type=ingested.source_type, source_url=ingested.source_url)

    return TranscribeResponse(
        song_id=song_id,
        title=title,
        difficulties={
            tier: DifficultyLink(musicxml_url=f"/storage/{song_id}/{tier}.musicxml")
            for tier in ("easy", "medium", "hard")
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: PASS (3 tests, including the original health check)

- [ ] **Step 5: Run the full backend test suite**

Run: `pytest -v`
Expected: PASS (all tests across every module in this plan)

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_api.py
git commit -m "feat: wire full pipeline into POST /transcribe"
```

---

## Task 16: Frontend Scaffold

**Files:**
- Create: `frontend/` (via Vite scaffolding)

- [ ] **Step 1: Scaffold the Vite + React + TypeScript project**

Run (from repo root):
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install axios opensheetmusicdisplay html5-qrcode
```

- [ ] **Step 2: Verify the dev server runs**

Run: `npm run dev`
Expected: Vite prints a local URL (e.g. `http://localhost:5173/`). Open it in a browser and confirm the default Vite+React starter page loads. Stop the server (Ctrl+C) once confirmed.

- [ ] **Step 3: Commit**

```bash
git add frontend/
git commit -m "chore: scaffold Vite + React + TypeScript frontend"
```

---

## Task 17: Frontend — API Client and Types

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/transcribe.ts`

**Interfaces:**
- Produces: `Difficulty` type (`"easy" | "medium" | "hard"`); `TranscribeResponse` interface; `transcribeFile(file: File): Promise<TranscribeResponse>`; `transcribeLink(url: string): Promise<TranscribeResponse>`.

- [ ] **Step 1: Write the types**

`frontend/src/api/types.ts`:
```typescript
export type Difficulty = "easy" | "medium" | "hard";

export interface DifficultyLink {
  musicxml_url: string;
}

export interface TranscribeResponse {
  song_id: string;
  title: string;
  difficulties: Record<Difficulty, DifficultyLink>;
}
```

- [ ] **Step 2: Write the API client**

`frontend/src/api/transcribe.ts`:
```typescript
import axios from "axios";
import type { TranscribeResponse } from "./types";

const API_BASE_URL = "http://localhost:8000";

export async function transcribeFile(file: File): Promise<TranscribeResponse> {
  const form = new FormData();
  form.append("audio_file", file);
  const response = await axios.post<TranscribeResponse>(
    `${API_BASE_URL}/transcribe`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return response.data;
}

export async function transcribeLink(url: string): Promise<TranscribeResponse> {
  const form = new FormData();
  if (url.includes("spotify.com")) {
    form.append("spotify_url", url);
  } else {
    form.append("youtube_url", url);
  }
  const response = await axios.post<TranscribeResponse>(
    `${API_BASE_URL}/transcribe`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return response.data;
}
```

- [ ] **Step 3: Verify it compiles**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/
git commit -m "feat: frontend API client for POST /transcribe"
```

---

## Task 18: Frontend — ScoreViewer Component

**Files:**
- Create: `frontend/src/components/ScoreViewer.tsx`

**Interfaces:**
- Produces: `ScoreViewer({ musicXmlUrl: string })` — React component that loads and renders a MusicXML URL via OpenSheetMusicDisplay.

- [ ] **Step 1: Write the component**

`frontend/src/components/ScoreViewer.tsx`:
```typescript
import { useEffect, useRef } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

interface ScoreViewerProps {
  musicXmlUrl: string;
}

export function ScoreViewer({ musicXmlUrl }: ScoreViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const osmd = new OpenSheetMusicDisplay(containerRef.current);
    let cancelled = false;

    (async () => {
      const fullUrl = musicXmlUrl.startsWith("http")
        ? musicXmlUrl
        : `http://localhost:8000${musicXmlUrl}`;
      await osmd.load(fullUrl);
      if (!cancelled) {
        osmd.render();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [musicXmlUrl]);

  return <div ref={containerRef} />;
}
```

- [ ] **Step 2: Verify it compiles**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no type errors.

- [ ] **Step 3: Manually verify rendering against a real score**

1. Start the backend: `cd backend && source .venv/bin/activate && uvicorn app.main:app --reload`
2. In a separate terminal, POST a test file to get a real `song_id`:
   ```bash
   curl -F "audio_file=@/path/to/any/short/piano.wav" http://localhost:8000/transcribe
   ```
   Note the `song_id` from the JSON response.
3. Temporarily edit `frontend/src/App.tsx` to render:
   ```typescript
   import { ScoreViewer } from "./components/ScoreViewer";

   function App() {
     return <ScoreViewer musicXmlUrl="/storage/PASTE_SONG_ID_HERE/easy.musicxml" />;
   }

   export default App;
   ```
4. Run: `npm run dev`, open the printed URL in a browser.
   Expected: rendered sheet music appears (treble + bass staves, notes visible).
5. Revert the temporary `App.tsx` edit (it will be rebuilt properly in Task 21).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ScoreViewer.tsx
git commit -m "feat: ScoreViewer component (OpenSheetMusicDisplay wrapper)"
```

---

## Task 19: Frontend — Upload Form (File + Link Input)

**Files:**
- Create: `frontend/src/components/UploadForm.tsx`

**Interfaces:**
- Consumes: `transcribeFile`, `transcribeLink` from `frontend/src/api/transcribe.ts`.
- Produces: `UploadForm({ onSuccess: (result: TranscribeResponse) => void })` — React component with a file picker and a link-paste form, showing loading/error state.

- [ ] **Step 1: Write the component**

`frontend/src/components/UploadForm.tsx`:
```typescript
import { useState } from "react";
import { transcribeFile, transcribeLink } from "../api/transcribe";
import type { TranscribeResponse } from "../api/types";

interface UploadFormProps {
  onSuccess: (result: TranscribeResponse) => void;
}

function extractErrorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response
    ?.data?.detail;
  return detail ?? "Something went wrong transcribing that audio.";
}

export function UploadForm({ onSuccess }: UploadFormProps) {
  const [link, setLink] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runTranscription(call: () => Promise<TranscribeResponse>) {
    setLoading(true);
    setError(null);
    try {
      const result = await call();
      onSuccess(result);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    await runTranscription(() => transcribeFile(file));
  }

  async function handleLinkSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!link.trim()) return;
    await runTranscription(() => transcribeLink(link.trim()));
  }

  return (
    <div>
      <input type="file" accept=".wav,.mp3" onChange={handleFileChange} />
      <form onSubmit={handleLinkSubmit}>
        <input
          type="text"
          placeholder="Paste a YouTube or Spotify link"
          value={link}
          onChange={(e) => setLink(e.target.value)}
        />
        <button type="submit">Transcribe</button>
      </form>
      {loading && <p>Transcribing…</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/UploadForm.tsx
git commit -m "feat: UploadForm component (file upload + link paste)"
```

---

## Task 20: Frontend — QR Scan Button

**Files:**
- Create: `frontend/src/components/QrScanButton.tsx`

**Interfaces:**
- Consumes: `transcribeLink` from `frontend/src/api/transcribe.ts`.
- Produces: `QrScanButton({ onSuccess: (result: TranscribeResponse) => void })` — React component that scans a QR code via webcam, decodes it to a link, and submits it through the same link-transcription path as `UploadForm`.

- [ ] **Step 1: Write the component**

`frontend/src/components/QrScanButton.tsx`:
```typescript
import { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { transcribeLink } from "../api/transcribe";
import type { TranscribeResponse } from "../api/types";

interface QrScanButtonProps {
  onSuccess: (result: TranscribeResponse) => void;
}

const SCANNER_ELEMENT_ID = "qr-scanner-region";

function extractErrorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response
    ?.data?.detail;
  return detail ?? "Couldn't transcribe the scanned link.";
}

export function QrScanButton({ onSuccess }: QrScanButtonProps) {
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scannerRef = useRef<Html5Qrcode | null>(null);

  useEffect(() => {
    if (!scanning) return;

    const scanner = new Html5Qrcode(SCANNER_ELEMENT_ID);
    scannerRef.current = scanner;

    scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: 250 },
        async (decodedText) => {
          await scanner.stop();
          setScanning(false);
          try {
            const result = await transcribeLink(decodedText);
            onSuccess(result);
          } catch (err) {
            setError(extractErrorMessage(err));
          }
        },
        () => {
          // per-frame scan failure — ignored, scanning continues
        }
      )
      .catch(() => setError("Could not access the camera."));

    return () => {
      scannerRef.current?.stop().catch(() => {});
    };
  }, [scanning]);

  return (
    <div>
      <button onClick={() => setScanning(true)}>Scan QR code</button>
      {scanning && <div id={SCANNER_ELEMENT_ID} />}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no type errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/QrScanButton.tsx
git commit -m "feat: QrScanButton component (scan-to-link input)"
```

---

## Task 21: Frontend — Difficulty Tabs and App Integration (End-to-End)

**Files:**
- Create: `frontend/src/components/DifficultyTabs.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `ScoreViewer` (Task 18), `UploadForm` (Task 19), `QrScanButton` (Task 20), `TranscribeResponse`/`Difficulty` (Task 17).
- Produces: `DifficultyTabs({ result: TranscribeResponse })`; the fully wired `App` component.

- [ ] **Step 1: Write DifficultyTabs**

`frontend/src/components/DifficultyTabs.tsx`:
```typescript
import { useState } from "react";
import { ScoreViewer } from "./ScoreViewer";
import type { Difficulty, TranscribeResponse } from "../api/types";

interface DifficultyTabsProps {
  result: TranscribeResponse;
}

const TIERS: Difficulty[] = ["easy", "medium", "hard"];

export function DifficultyTabs({ result }: DifficultyTabsProps) {
  const [active, setActive] = useState<Difficulty>("easy");

  return (
    <div>
      <div role="tablist">
        {TIERS.map((tier) => (
          <button
            key={tier}
            role="tab"
            aria-selected={active === tier}
            onClick={() => setActive(tier)}
          >
            {tier[0].toUpperCase() + tier.slice(1)}
          </button>
        ))}
      </div>
      <ScoreViewer musicXmlUrl={result.difficulties[active].musicxml_url} />
    </div>
  );
}
```

- [ ] **Step 2: Wire App.tsx**

`frontend/src/App.tsx`:
```typescript
import { useState } from "react";
import { UploadForm } from "./components/UploadForm";
import { QrScanButton } from "./components/QrScanButton";
import { DifficultyTabs } from "./components/DifficultyTabs";
import type { TranscribeResponse } from "./api/types";

function App() {
  const [result, setResult] = useState<TranscribeResponse | null>(null);

  return (
    <div>
      <h1>Synthony</h1>
      {!result && (
        <>
          <UploadForm onSuccess={setResult} />
          <QrScanButton onSuccess={setResult} />
        </>
      )}
      {result && <DifficultyTabs result={result} />}
    </div>
  );
}

export default App;
```

- [ ] **Step 3: Verify it compiles**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no type errors.

- [ ] **Step 4: Manual end-to-end verification**

1. Start the backend: `cd backend && source .venv/bin/activate && uvicorn app.main:app --reload`
2. Start the frontend: `cd frontend && npm run dev`
3. Open the printed frontend URL in a browser.
4. Use the file picker to upload a short solo piano WAV or MP3 recording.
5. Expected: a brief "Transcribing…" message, then three tabs — Easy, Medium, Hard — appear.
6. Click each tab. Expected: each renders distinct, readable sheet music via OpenSheetMusicDisplay — Easy visibly simpler (narrower range, sparser rhythm) than Hard.
7. Reload the page and try the link-paste field with a YouTube URL of a solo piano performance. Expected: same three-tab result after transcription completes.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DifficultyTabs.tsx frontend/src/App.tsx
git commit -m "feat: wire difficulty tabs and full frontend flow end-to-end"
```
