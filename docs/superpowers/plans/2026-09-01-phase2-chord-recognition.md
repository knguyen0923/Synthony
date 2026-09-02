# Chord Recognition (Spec 2, Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the chord-recognition module: chroma-feature extraction
plus template matching over an audio file (in production, a separated
bass+other harmony stem), quantized to a chord-per-bar sequence, producing
the `ChordSymbol` list the already-built arrangement engine (Phase 3)
consumes.

**Architecture:** A new `backend/app/chords/` package. The chord-template
matching logic (`match_chord`) is a pure function — given a 12-bin chroma
vector, return the best-matching `(root, quality)` — and is the
highest-value, exactly-testable unit, same philosophy as Phase 3's
arrangement engine. The audio-facing `detect_chords` wraps `librosa`
chroma/beat extraction around it and is tested loosely against a synthetic
fixture, per the spec's Testing Strategy. This package reuses
`ChordSymbol` and the chord-quality interval table from
`app.arrangement.theory` rather than redefining them.

**Tech Stack:** Python, `librosa` (existing dependency), `numpy`
(existing), `pytest`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-01-any-song-arrangement-design.md`
(see "New Components" → Chord recognition, "Phased Roadmap" → Phase 2,
"Testing Strategy").

**Phase 0 spike findings this plan builds on** (see prior spike report):
chroma + template matching got ~70-75% root accuracy on piano-dominant
material but degraded on guitar/vocal-dense mixes when run on the full
mix, with two specific failure modes: (1) **relative-key/7th-chord
flicker** — a plain triad's chroma also partially matches its own 7th
superset template, causing spurious major→maj7/dom7 misfires — and (2)
raw per-beat matching is noisy. This plan directly addresses both:
aggregating chroma over 4-beat bars instead of raw beats, and requiring a
similarity margin before a 7th-quality template can win over its
corresponding triad. (Running on separated stems instead of the full mix,
the spike's third recommendation, is a production-wiring concern for
Phase 4, not something this module — which just takes an audio path —
needs to know about.)

## Global Constraints

- Deterministic, non-ML: chroma extraction + cosine-similarity template
  matching only, no training data, per the spec's "Deterministic, non-ML
  arrangement and chord recognition" decision.
- Reuse `ChordSymbol` from `app.arrangement.types` and chord-quality
  intervals from `app.arrangement.theory.CHORD_INTERVALS` — do not
  redefine either.
- No new dependencies — `librosa` and `numpy` are already in
  `backend/requirements.txt`.
- The pure matching function (`match_chord`) is tested with hand-crafted
  chroma vectors and exact expected output. The audio-facing function
  (`detect_chords`) is tested loosely against the existing
  `synthetic_piano_wav` fixture, per the spec's Testing Strategy.

---

## File Structure

- Create: `backend/app/chords/__init__.py`
- Create: `backend/app/chords/templates.py` — chord-template vectors
- Create: `backend/app/chords/match.py` — `match_chord`
- Create: `backend/app/chords/detect.py` — `detect_chords`,
  `_merge_consecutive`
- Create: `backend/tests/test_chords_match.py`
- Create: `backend/tests/test_chords_detect.py`

## Task 1: Chord templates and margin-based matching

**Files:**
- Create: `backend/app/chords/__init__.py`
- Create: `backend/app/chords/templates.py`
- Create: `backend/app/chords/match.py`
- Test: `backend/tests/test_chords_match.py`

**Interfaces:**
- Consumes: `chord_tones` from `app.arrangement.theory` (existing, from
  the already-merged Phase 3 arrangement engine).
- Produces: `TEMPLATES: dict[tuple[int, str], np.ndarray]` in
  `app.chords.templates` — one unit-norm 12-bin chroma vector per
  `(root, quality)` pair, `root` 0-11, `quality` one of `"major"`,
  `"minor"`, `"dim"`, `"dom7"`, `"maj7"`, `"min7"`.
- Produces: `BASE_TRIAD: dict[str, str]` in `app.chords.templates` —
  maps each 7th quality to its corresponding triad quality
  (`"dom7"→"major"`, `"maj7"→"major"`, `"min7"→"minor"`).
- Produces: `match_chord(chroma_vector: np.ndarray) -> tuple[int, str]`
  in `app.chords.match`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_chords_match.py
import numpy as np

from app.chords.match import match_chord


def test_match_chord_identifies_pure_c_major_triad():
    chroma = np.zeros(12)
    for pitch_class in (0, 4, 7):  # C, E, G
        chroma[pitch_class] = 1.0
    assert match_chord(chroma) == (0, "major")


def test_match_chord_identifies_a_minor_triad():
    chroma = np.zeros(12)
    for pitch_class in (9, 0, 4):  # A, C, E
        chroma[pitch_class] = 1.0
    assert match_chord(chroma) == (9, "minor")


def test_match_chord_identifies_dominant_seventh_when_clearly_present():
    chroma = np.zeros(12)
    for pitch_class in (0, 4, 7, 10):  # C dominant 7th: C E G Bb
        chroma[pitch_class] = 1.0
    assert match_chord(chroma) == (0, "dom7")


def test_match_chord_distinguishes_major_seventh_from_dominant_seventh():
    chroma = np.zeros(12)
    for pitch_class in (0, 4, 7, 11):  # C major 7th: C E G B
        chroma[pitch_class] = 1.0
    assert match_chord(chroma) == (0, "maj7")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_match.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.chords'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/chords/templates.py
import numpy as np

from app.arrangement.theory import chord_tones

QUALITIES = ("major", "minor", "dim", "dom7", "maj7", "min7")
# Each 7th quality's corresponding triad quality (same root), used by
# match_chord's margin rule.
BASE_TRIAD: dict[str, str] = {"dom7": "major", "maj7": "major", "min7": "minor"}


def _template_vector(root: int, quality: str) -> np.ndarray:
    vector = np.zeros(12)
    for pitch_class in chord_tones(root, quality):
        vector[pitch_class] = 1.0
    return vector / np.linalg.norm(vector)


TEMPLATES: dict[tuple[int, str], np.ndarray] = {
    (root, quality): _template_vector(root, quality)
    for root in range(12)
    for quality in QUALITIES
}
```

```python
# backend/app/chords/match.py
import numpy as np

from app.chords.templates import BASE_TRIAD, TEMPLATES

# A plain triad's chroma also partially matches its own 7th-chord
# superset template (3 of the 7th's 4 tones are already present) — this
# caused spurious 7th-chord flicker during the Phase 0 spike. A 7th
# quality only wins over its corresponding triad (same root) if it's more
# than this much more similar.
SEVENTH_MARGIN = 0.05


def match_chord(chroma_vector: np.ndarray) -> tuple[int, str]:
    """Match a 12-bin chroma vector to the closest (root, quality) chord
    template by cosine similarity."""
    norm = np.linalg.norm(chroma_vector)
    normalized = chroma_vector / norm if norm > 0 else chroma_vector

    similarities = {
        key: float(np.dot(normalized, template))
        for key, template in TEMPLATES.items()
    }

    best_key = max(similarities, key=similarities.get)
    best_root, best_quality = best_key

    base_triad = BASE_TRIAD.get(best_quality)
    if base_triad is not None:
        triad_similarity = similarities[(best_root, base_triad)]
        if similarities[best_key] - triad_similarity <= SEVENTH_MARGIN:
            return best_root, base_triad

    return best_root, best_quality
```

```bash
touch backend/app/chords/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_match.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/chords/__init__.py backend/app/chords/templates.py backend/app/chords/match.py backend/tests/test_chords_match.py
git commit -m "feat: add chord templates and margin-based chord matching"
```

## Task 2: Bar-level chord detection over audio

**Files:**
- Create: `backend/app/chords/detect.py`
- Test: `backend/tests/test_chords_detect.py`

**Interfaces:**
- Consumes: `match_chord` (Task 1), `ChordSymbol` from
  `app.arrangement.types` (existing).
- Produces: `_merge_consecutive(chords: list[ChordSymbol]) -> list[ChordSymbol]`
  — collapses adjacent chords of the same `(root, quality)` into one
  longer `ChordSymbol`.
- Produces: `detect_chords(audio_path: str) -> list[ChordSymbol]` — the
  module's public entry point.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_chords_detect.py
from app.arrangement.types import ChordSymbol
from app.chords.detect import _merge_consecutive, detect_chords


def test_merge_consecutive_combines_matching_adjacent_chords():
    chords = [
        ChordSymbol(start=0.0, duration=2.0, root=0, quality="major"),
        ChordSymbol(start=2.0, duration=2.0, root=0, quality="major"),
        ChordSymbol(start=4.0, duration=2.0, root=7, quality="major"),
    ]
    merged = _merge_consecutive(chords)
    assert merged == [
        ChordSymbol(start=0.0, duration=4.0, root=0, quality="major"),
        ChordSymbol(start=4.0, duration=2.0, root=7, quality="major"),
    ]


def test_detect_chords_returns_a_sequence_covering_the_clip(synthetic_piano_wav):
    chords = detect_chords(str(synthetic_piano_wav))

    assert len(chords) >= 1
    assert chords[0].start == 0.0
    assert chords[-1].start + chords[-1].duration <= 2.5  # clip is 2s, allow rounding slack
    for chord in chords:
        assert 0 <= chord.root <= 11
        assert chord.quality in ("major", "minor", "dim", "dom7", "maj7", "min7")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_detect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.chords.detect'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/chords/detect.py
import librosa
import numpy as np

from app.arrangement.types import ChordSymbol
from app.chords.match import match_chord

BEATS_PER_BAR = 4  # assumes 4/4 time — a fixed-grid simplification, same
                    # spirit as the rest of this codebase's fixed-tempo
                    # assumptions


def detect_chords(audio_path: str) -> list[ChordSymbol]:
    """Detect a chord-per-bar sequence from an audio file: chroma
    features aggregated over 4-beat bars, matched against chord
    templates, with consecutive identical chords merged into one
    ChordSymbol."""
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration = len(y) / sr

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    _tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
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

    return _merge_consecutive(raw_chords)


def _merge_consecutive(chords: list[ChordSymbol]) -> list[ChordSymbol]:
    if not chords:
        return []

    merged = [chords[0]]
    for chord in chords[1:]:
        last = merged[-1]
        if chord.root == last.root and chord.quality == last.quality:
            merged[-1] = ChordSymbol(
                start=last.start,
                duration=last.duration + chord.duration,
                root=last.root,
                quality=last.quality,
            )
        else:
            merged.append(chord)
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_detect.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full arrangement + chords test suite, then the full backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_match.py tests/test_chords_detect.py -v`
Expected: PASS (6 tests total)

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all tests pass, nothing existing broken (this plan only adds
new files under `backend/app/chords/` and `backend/tests/`)

- [ ] **Step 6: Commit**

```bash
git add backend/app/chords/detect.py backend/tests/test_chords_detect.py
git commit -m "feat: add bar-level chord detection over audio"
```

## Out of Scope for This Plan

- Running `detect_chords` on a separated harmony (bass+other) stem
  specifically rather than a full mix — this module just takes an audio
  path; which audio it's given is a Phase 4 (async job) wiring decision,
  informed by the Phase 0 spike's recommendation to use separated stems in
  production.
- Feeding `detect_chords`'s output into the Phase 3 arrangement engine's
  `generate_lh_variants` — that's also Phase 4 wiring, once melody
  extraction (Phase 1) and this module both exist as building blocks.
- Key detection / relative major-minor disambiguation beyond the
  margin-based 7th-vs-triad fix — the spike flagged relative-key confusion
  (F↔Dm7, G↔Em) as a real failure mode, but fixing it needs a key-aware
  pass, which the spec doesn't scope into Phase 2 and isn't blocking:
  Phase 5's quality-iteration-by-ear is where that gets tuned.
