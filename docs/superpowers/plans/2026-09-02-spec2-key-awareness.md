# Key-Aware Chord Smoothing for Spec 2 (Phase 5 quality) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce chord-detection errors — by-ear feedback (Phase 5) said
"chords don't quite match" the real song. The Phase 0 spike already
flagged the specific failure mode: relative major/minor confusion (e.g.
F↔Dm7, G↔Em) — the detector has no notion of what key the song is in, so
it can't rule out chords that don't actually fit the song's tonality.

**Architecture:** A new `app/chords/key.py` module estimates the song's
key (tonic + major/minor) once, from the harmony stem's overall chroma
distribution, using Krumhansl-Schmuckler key-profile correlation — a
classic, deterministic, well-established music-theory technique (not
ML), consistent with this codebase's existing chroma/template-matching
approach to chord detection. `match_chord` (`app/chords/match.py`) gains
an optional `key` parameter: a chord that's diatonic to the detected key
gets a small similarity bonus, nudging close calls toward the chord that
actually fits the song rather than an equally-plausible-by-chroma-alone
but harmonically implausible one. `detect_chords` computes the key once
per song and passes it into every bar's `match_chord` call.

**Tech Stack:** Python, `numpy` (already a dependency — used for the
correlation).

**Spec:** No formal design doc — direct Phase 5 by-ear tuning work agreed
in conversation. Reference the Phase 0 spike findings (relayed in
conversation, not a file) for the specific failure mode this targets.

## Prerequisite: confirm your worktree has the real-tempo work merged

This plan modifies `detect_chords`, which the real-tempo plan already
changed. Before starting Task 1, confirm your worktree's
`app/chords/detect.py` already returns a tuple (run
`grep -n "def detect_chords" backend/app/chords/detect.py`):

```python
def detect_chords(audio_path: str) -> tuple[list[ChordSymbol], float]:
```

If you instead see `def detect_chords(audio_path: str) -> list[ChordSymbol]:`
(no tuple), your worktree is stale. Merge in
`origin/spec-1-solo-piano-pipeline` first (`git merge origin/spec-1-solo-piano-pipeline --no-edit`),
then re-check. **Do not lose the tempo-returning behavior** — this
plan's changes to `detect_chords` must be layered on top of that
existing tuple return, not replace it.

## Global Constraints

- Key detection is a whole-song estimate computed **once** per
  `detect_chords` call (from the same chroma matrix already extracted),
  not re-estimated per bar.
- The diatonic bonus is a small nudge (`DIATONIC_BONUS = 0.05`), not an
  override — it should break close ties toward the harmonically
  plausible reading, not force a diatonic chord when the chroma evidence
  clearly points elsewhere (e.g. a genuine borrowed/chromatic chord).
- This plan does not touch tempo threading or dynamics — those are
  separate, parallel Phase 5 plans. Don't modify `_tempo_to_seconds_per_quarter`
  or anything about the tempo return value.
- The Krumhansl-Kessler key-profile values used below are long-published,
  standard empirical constants from music cognition research — not
  copyrighted creative content, safe to use as-is.

---

## File Structure

- Create: `app/chords/key.py`
- Modify: `app/chords/match.py` (`match_chord` gains an optional `key`
  parameter)
- Modify: `app/chords/detect.py` (`detect_chords` estimates the key once
  and passes it to `match_chord`)
- Create: `backend/tests/test_chords_key.py`
- Modify: `backend/tests/test_chords_match.py`, `test_chords_detect.py`

## Task 1: Key detection

**Files:**
- Create: `app/chords/key.py`
- Create: `backend/tests/test_chords_key.py`

**Interfaces:**
- Produces: `detect_key(chroma: np.ndarray) -> tuple[int, str]` — returns
  `(tonic_pitch_class, "major" | "minor")`.
- Produces: `is_diatonic(root: int, quality: str, key: tuple[int, str]) -> bool`
  — whether `(root, quality)` is a plausible diatonic chord in `key`. A
  7th-quality chord is checked against its corresponding triad quality
  (reusing `app.chords.templates.BASE_TRIAD`, the same collapsing
  `match_chord` already does for its own margin rule).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_chords_key.py
import numpy as np

from app.chords.key import MAJOR_PROFILE, MINOR_PROFILE, detect_key, is_diatonic


def test_detect_key_recovers_a_rotated_major_profile():
    rotated = np.roll(MAJOR_PROFILE, 4)  # simulate a song centered on E major (tonic=4)
    chroma = rotated.reshape(12, 1)
    assert detect_key(chroma) == (4, "major")


def test_detect_key_recovers_a_rotated_minor_profile():
    rotated = np.roll(MINOR_PROFILE, 9)  # simulate a song centered on A minor (tonic=9)
    chroma = rotated.reshape(12, 1)
    assert detect_key(chroma) == (9, "minor")


def test_is_diatonic_accepts_the_tonic_major_triad_in_a_major_key():
    assert is_diatonic(0, "major", (0, "major")) is True  # I


def test_is_diatonic_accepts_the_relative_minor_in_a_major_key():
    assert is_diatonic(9, "minor", (0, "major")) is True  # vi


def test_is_diatonic_rejects_a_non_diatonic_chord():
    assert is_diatonic(1, "major", (0, "major")) is False  # bII, not diatonic to C major


def test_is_diatonic_collapses_a_seventh_to_its_triad_quality():
    assert is_diatonic(7, "dom7", (0, "major")) is True  # V7 in C major — dom7 collapses to major (V)


def test_is_diatonic_works_for_minor_keys():
    assert is_diatonic(0, "minor", (0, "minor")) is True   # i
    assert is_diatonic(5, "minor", (0, "minor")) is True   # iv
    assert is_diatonic(1, "major", (0, "minor")) is False  # not diatonic to C minor
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_key.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.chords.key'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/chords/key.py
import numpy as np

from app.chords.templates import BASE_TRIAD

# Krumhansl-Kessler key profiles — standard, published empirical
# constants from music cognition research (relative perceived
# "fit" of each pitch class to a major/minor tonal center), used
# here via correlation against a song's overall chroma distribution
# to estimate its key.
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# Expected triad quality at each diatonic scale degree (0-indexed
# semitone offset from the tonic), for major and natural-minor keys —
# the standard classical/pop harmony convention (I-ii-iii-IV-V-vi-vii°
# in major; i-ii°-III-iv-v-VI-VII in natural minor).
MAJOR_DIATONIC_QUALITIES = {0: "major", 2: "minor", 4: "minor", 5: "major", 7: "major", 9: "minor", 11: "dim"}
MINOR_DIATONIC_QUALITIES = {0: "minor", 2: "dim", 3: "major", 5: "minor", 7: "minor", 8: "major", 10: "major"}


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


def is_diatonic(root: int, quality: str, key: tuple[int, str]) -> bool:
    """Whether (root, quality) is a plausible diatonic chord in `key`."""
    tonic, mode = key
    degree = (root - tonic) % 12
    table = MAJOR_DIATONIC_QUALITIES if mode == "major" else MINOR_DIATONIC_QUALITIES
    expected = table.get(degree)
    if expected is None:
        return False
    triad_quality = BASE_TRIAD.get(quality, quality)
    return triad_quality == expected
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_key.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/chords/key.py backend/tests/test_chords_key.py
git commit -m "feat: add Krumhansl-Schmuckler key detection and diatonic-chord check"
```

## Task 2: Wire the key bias into `match_chord` and `detect_chords`

**Files:**
- Modify: `app/chords/match.py`
- Modify: `app/chords/detect.py`
- Modify: `backend/tests/test_chords_match.py`
- Modify: `backend/tests/test_chords_detect.py`

**Interfaces:**
- Modifies: `match_chord(chroma_vector: np.ndarray, key: Optional[tuple[int, str]] = None) -> tuple[int, str]`
  — when `key` is given, a diatonic candidate's similarity gets
  `+ DIATONIC_BONUS` before picking the best match (and before the
  existing 7th-vs-triad margin check, which still runs exactly as
  before on the now-possibly-bonused similarities).
- Modifies: `detect_chords` — calls `detect_key(chroma)` once, passes the
  result to every `match_chord(bar_chroma, key=key)` call.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_chords_match.py`:

```python
def test_match_chord_accepts_an_optional_key_without_changing_a_clear_match():
    chroma = np.zeros(12)
    for pitch_class in (0, 4, 7):
        chroma[pitch_class] = 1.0
    # A key where C major isn't even diatonic shouldn't override an
    # unambiguous, exact chroma match.
    assert match_chord(chroma, key=(6, "major")) == (0, "major")


def test_match_chord_key_bias_does_not_break_the_no_key_default():
    chroma = np.zeros(12)
    for pitch_class in (9, 0, 4):
        chroma[pitch_class] = 1.0
    assert match_chord(chroma) == (9, "minor")
```

Add to `backend/tests/test_chords_detect.py`:

```python
def test_detect_chords_still_returns_a_sequence_and_tempo_with_key_bias_wired_in(synthetic_piano_wav):
    # Regression check: wiring in key detection must not break the
    # existing contract (this duplicates the shape of the existing
    # tempo-covering test deliberately, as a belt-and-suspenders check
    # that detect_chords's key-detection call doesn't raise on real
    # audio input).
    chords, seconds_per_quarter = detect_chords(str(synthetic_piano_wav))
    assert len(chords) >= 1
    assert seconds_per_quarter > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_match.py tests/test_chords_detect.py -v -k "key"`
Expected: FAIL — `TypeError: match_chord() got an unexpected keyword argument 'key'`
for the match.py tests. The detect.py regression test should actually
already pass at this point (it's just re-checking the existing
contract) — that's fine, it'll keep passing after Task 2's changes too.

- [ ] **Step 3: Write minimal implementation**

In `app/chords/match.py`, change the imports and `match_chord`:

```python
from typing import Optional

import numpy as np

from app.chords.key import is_diatonic
from app.chords.templates import BASE_TRIAD, TEMPLATES

SEVENTH_MARGIN = 0.05
# A small nudge — enough to break a close tie toward a chord that
# actually fits the song's detected key, not enough to override a
# clearly better chroma match (a genuine borrowed/chromatic chord).
DIATONIC_BONUS = 0.05


def match_chord(chroma_vector: np.ndarray, key: Optional[tuple[int, str]] = None) -> tuple[int, str]:
    """Match a 12-bin chroma vector to the closest (root, quality) chord
    template by cosine similarity, optionally biased toward chords
    diatonic to a given key."""
    norm = np.linalg.norm(chroma_vector)
    normalized = chroma_vector / norm if norm > 0 else chroma_vector

    similarities = {}
    for key_, template in TEMPLATES.items():
        score = float(np.dot(normalized, template))
        if key is not None and is_diatonic(*key_, key):
            score += DIATONIC_BONUS
        similarities[key_] = score

    best_key = max(similarities, key=similarities.get)
    best_root, best_quality = best_key

    base_triad = BASE_TRIAD.get(best_quality)
    if base_triad is not None:
        triad_similarity = similarities[(best_root, base_triad)]
        if similarities[best_key] - triad_similarity <= SEVENTH_MARGIN:
            return best_root, base_triad

    return best_root, best_quality
```

In `app/chords/detect.py`, add the import and wire it in:

```python
from app.chords.key import detect_key
```

Change the body of `detect_chords` — add the `key = detect_key(chroma)`
line right after `chroma` is computed, and pass `key=key` into the
existing `match_chord(bar_chroma)` call:

```python
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    key = detect_key(chroma)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
```

```python
        bar_chroma = chroma[:, in_bar].mean(axis=1)
        root, quality = match_chord(bar_chroma, key=key)
```

Every other line in `detect_chords` (the tempo handling, bar-building,
`_merge_consecutive`/`_absorb_short_chords` calls, the final `return
chords, seconds_per_quarter`) stays exactly as it is right now — this
task only adds the `key` computation and threads it into the one
`match_chord` call.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_match.py tests/test_chords_detect.py -v`
Expected: PASS (full contents of both files)

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all tests pass, nothing else broken.

- [ ] **Step 6: Commit**

```bash
git add backend/app/chords/match.py backend/app/chords/detect.py backend/tests/test_chords_match.py backend/tests/test_chords_detect.py
git commit -m "feat: bias chord matching toward the song's detected key"
```

## Task 3: Verify against a real song

**Files:** none — verification only.

- [ ] **Step 1: Run `detect_key` + `detect_chords` against a real
  harmony stem already on disk**

```bash
find backend/storage -name harmony.wav | head -3
```

From `backend/`:

```bash
./.venv/bin/python -c "
import librosa
from app.chords.key import detect_key
from app.chords.detect import detect_chords

path = 'storage/<a song_id from above>/stems/harmony.wav'
y, sr = librosa.load(path, sr=None, mono=True)
chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
tonic, mode = detect_key(chroma)
print('detected key:', ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'][tonic], mode)

chords, spq = detect_chords(path)
for c in chords:
    print(f'  start={c.start:.2f} dur={c.duration:.2f} root={c.root} quality={c.quality}')
"
```

Expected: a plausible key name printed, and a chord list — report both
in your final summary. This is a sanity check that key detection
produces a musically reasonable result on real audio, not a strict pass/
fail assertion (correctness here is ultimately a by-ear judgment for the
coordinator/user, same as the rest of Phase 5).

## Out of Scope for This Plan

- Modeling more than triad-level diatonic expectations (e.g. secondary
  dominants, borrowed chords, modal interchange) — the diatonic table
  here is intentionally the simple, standard 7-chord-per-key model.
- Re-tuning `DIATONIC_BONUS` by ear against real songs — that's a
  follow-up once this lands and the coordinator/user can listen.
- Tempo threading and dynamics — separate, parallel Phase 5 plans.
