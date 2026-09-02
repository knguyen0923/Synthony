# Apply Detected Key Signature to Exported Score (Phase 5 quality) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the song's already-detected key to the exported score as a
real key signature, instead of every non-C-major note being spelled out
with an individual accidental. The key is already computed (Krumhansl-
Schmuckler key detection, wired into `detect_chords` for chord-matching
bias) but currently discarded after that one use — this plan surfaces it
and applies it to notation.

**Architecture:** `detect_chords` gains a third return value (the
detected key), alongside its existing `(chords, seconds_per_quarter)`.
`app/notation/hand_split.py` gains a small helper,
`key_signature_from_tonic`, converting a `(pitch_class, mode)` pair into
a `music21.key.Key` object, and `build_grand_staff_score` gains an
optional `key_signature` parameter that inserts it into both staves.
`arrange_pipeline.py` threads the detected key through.

**Tech Stack:** Python, `music21` (existing — `music21.key.Key` and
`music21.pitch.Pitch` are standard APIs).

**Spec:** No formal design doc — direct Phase 5 by-ear tuning work agreed
in conversation.

## Prerequisite: confirm your worktree has the tempo + key-awareness work merged

Before starting Task 1, confirm `app/chords/detect.py`'s `detect_chords`
already returns `tuple[list[ChordSymbol], float]` (tempo work) and that
`app/chords/key.py` exists with a `detect_key` function (key-awareness
work) — run:

```bash
grep -n "def detect_chords" backend/app/chords/detect.py
ls backend/app/chords/key.py
```

If either is missing, merge in `origin/spec-1-solo-piano-pipeline` first.

## Global Constraints

- `detect_chords`'s return type changes from a 2-tuple to a 3-tuple —
  every call site (production and test) must be updated for this one
  breaking change.
- Enharmonic spelling (e.g. F# vs Gb) is not modeled carefully here —
  `music21.pitch.Pitch(midi=60 + tonic_pitch_class).name`'s default
  spelling is used as-is. This is a reasonable first pass; revisit only
  if by-ear/by-eye review of real output flags a specific song where the
  spelling reads oddly.
- This plan does not touch chord detection logic, tempo, or dynamics —
  purely surfacing an already-computed value and applying it to notation.

---

## File Structure

- Modify: `app/chords/detect.py` (`detect_chords` returns key too)
- Modify: `app/notation/hand_split.py` (new `key_signature_from_tonic`;
  `build_grand_staff_score` gains the parameter)
- Modify: `app/arrange_pipeline.py` (thread the key through)
- Modify: `backend/tests/test_chords_detect.py`, `test_hand_split.py`,
  `test_api.py`

## Task 1: `detect_chords` returns the detected key

**Files:**
- Modify: `app/chords/detect.py`
- Modify: `backend/tests/test_chords_detect.py`

**Interfaces:**
- Modifies: `detect_chords(audio_path: str) -> tuple[list[ChordSymbol], float, tuple[int, str]]`
  — now returns `(chords, seconds_per_quarter, key)`.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_chords_detect.py`, update both existing tests that
unpack `detect_chords`'s return value to unpack three values instead of
two:

```python
def test_detect_chords_returns_a_sequence_and_tempo_covering_the_clip(synthetic_piano_wav):
    chords, seconds_per_quarter, key = detect_chords(str(synthetic_piano_wav))

    assert len(chords) >= 1
    assert chords[0].start == 0.0
    assert chords[-1].start + chords[-1].duration <= 2.5  # clip is 2s, allow rounding slack
    for chord in chords:
        assert 0 <= chord.root <= 11
        assert chord.quality in ("major", "minor", "dim", "dom7", "maj7", "min7")
    assert seconds_per_quarter > 0
    tonic, mode = key
    assert 0 <= tonic <= 11
    assert mode in ("major", "minor")


def test_detect_chords_still_returns_a_sequence_and_tempo_with_key_bias_wired_in(synthetic_piano_wav):
    chords, seconds_per_quarter, key = detect_chords(str(synthetic_piano_wav))
    assert len(chords) >= 1
    assert seconds_per_quarter > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_detect.py -v`
Expected: FAIL — unpacking a 2-tuple into three variables raises
`ValueError: not enough values to unpack`.

- [ ] **Step 3: Write minimal implementation**

In `app/chords/detect.py`, change the final line of `detect_chords`:

```python
    chords = _absorb_short_chords(_merge_consecutive(raw_chords))
    return chords, seconds_per_quarter, key
```

(The `key = detect_key(chroma)` line already exists earlier in the
function from the key-awareness work — this task only changes the
`return` statement to also expose it. Nothing else in the function
changes.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_chords_detect.py -v`
Expected: PASS (full file)

- [ ] **Step 5: Commit**

```bash
git add backend/app/chords/detect.py backend/tests/test_chords_detect.py
git commit -m "feat: detect_chords also returns the song's detected key"
```

## Task 2: Apply the key signature to the exported score

**Files:**
- Modify: `app/notation/hand_split.py`
- Modify: `backend/tests/test_hand_split.py`

**Interfaces:**
- Produces: `key_signature_from_tonic(tonic_pitch_class: int, mode: str) -> key.Key`
  in `app.notation.hand_split`.
- Modifies: `build_grand_staff_score(rh: stream.Part, lh: stream.Part, title: Optional[str] = None, key_signature: Optional[key.Key] = None) -> stream.Score`
  — when `key_signature` is given, it's inserted into both the RH and LH
  parts (a separate deep copy for each, to avoid music21 site conflicts
  from inserting the same object into two streams).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_hand_split.py`:

```python
def test_key_signature_from_tonic_builds_g_major_one_sharp():
    k = key_signature_from_tonic(7, "major")
    assert k.tonic.name == "G"
    assert k.mode == "major"
    assert k.sharps == 1


def test_key_signature_from_tonic_builds_f_major_one_flat():
    k = key_signature_from_tonic(5, "major")
    assert k.tonic.name == "F"
    assert k.sharps == -1


def test_grand_staff_applies_a_given_key_signature_to_the_exported_musicxml():
    rh = stream.Part(id="RH")
    rh.insert(0, note.Note("C5"))
    lh = stream.Part(id="LH")
    lh.insert(0, note.Note("C3"))
    g_major = key_signature_from_tonic(7, "major")

    score = build_grand_staff_score(rh, lh, key_signature=g_major)

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_key_sig.musicxml"
        export_musicxml(score, output_path)
        xml = output_path.read_text()

    assert "<fifths>1</fifths>" in xml


def test_grand_staff_with_no_key_signature_given_stays_key_of_c():
    rh = stream.Part(id="RH")
    rh.insert(0, note.Note("C5"))
    lh = stream.Part(id="LH")
    lh.insert(0, note.Note("C3"))

    score = build_grand_staff_score(rh, lh)

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_no_key_sig.musicxml"
        export_musicxml(score, output_path)
        xml = output_path.read_text()

    assert "<fifths>0</fifths>" not in xml or "<key>" not in xml
```

(The last test is a loose regression check — its exact assertion doesn't
matter much as long as it confirms the no-`key_signature` code path,
which every existing caller uses, still exports successfully without
crashing. If `<key>` isn't present at all when no key signature is given,
that's the expected/correct behavior — adjust the assertion to
`assert "<key>" not in xml` if that's what you observe, whichever is
actually true is fine, just don't leave this test silently passing
without having actually run it once to see which branch is real.)

Add `from app.notation.hand_split import key_signature_from_tonic` to
this test file's existing import from that module (merge into the
existing `from app.notation.hand_split import ...` line rather than
adding a duplicate).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_hand_split.py -v -k key_sig`
Expected: FAIL — `ImportError: cannot import name 'key_signature_from_tonic'`

- [ ] **Step 3: Write minimal implementation**

In `app/notation/hand_split.py`, add `key` and `pitch` to the existing
`from music21 import ...` import line, and add `import copy` at the top
of the file if it isn't already imported (check first — this file may
not need it yet, difficulty files elsewhere in the codebase already use
this exact pattern for the same "avoid site conflicts by copying before
inserting into multiple streams" reason).

Add this function (anywhere in the module — e.g. right before
`build_grand_staff_score`):

```python
def key_signature_from_tonic(tonic_pitch_class: int, mode: str) -> key.Key:
    """Build a music21 Key (used as a key signature) from a detected
    (tonic pitch class, mode) pair, e.g. from app.chords.key.detect_key."""
    tonic_name = pitch.Pitch(midi=60 + tonic_pitch_class).name
    return key.Key(tonic_name, mode)
```

Change `build_grand_staff_score`'s signature and add the key-signature
insertion (everything else in the function body stays exactly as it is
— the clef-change logic, the brace/StaffGroup, the title metadata):

```python
def build_grand_staff_score(
    rh: stream.Part, lh: stream.Part, title: Optional[str] = None, key_signature: Optional[key.Key] = None
) -> stream.Score:
    """Assemble RH/LH parts into a Score with a piano brace connecting them,
    ...
    (existing docstring unchanged)
    """
    rh.partName = "Right Hand"
    rh.style.printPartName = False
    lh.partName = "Left Hand"
    lh.style.printPartName = False

    if key_signature is not None:
        rh.insert(0, copy.deepcopy(key_signature))
        lh.insert(0, copy.deepcopy(key_signature))

    _apply_dynamic_clef_changes(
        rh, clef.TrebleClef, clef.BassClef,
        is_away=lambda n: n.pitch.midi <= RH_LOW_REGISTER_THRESHOLD,
    )
    _apply_dynamic_clef_changes(
        lh, clef.BassClef, clef.TrebleClef,
        is_away=lambda n: n.pitch.midi >= LH_HIGH_REGISTER_THRESHOLD,
    )

    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)
    score.insert(0, layout.StaffGroup([rh, lh], name="Piano", abbreviation="Pno.", symbol="brace"))
    if title:
        score.metadata = metadata.Metadata()
        score.metadata.title = title
    return score
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_hand_split.py -v`
Expected: PASS (full file — confirms every existing Spec 1 and Spec 2
caller, none of which pass `key_signature`, still works unchanged)

- [ ] **Step 5: Commit**

```bash
git add backend/app/notation/hand_split.py backend/tests/test_hand_split.py
git commit -m "feat: add key_signature_from_tonic and apply it in build_grand_staff_score"
```

## Task 3: Wire the detected key through `arrange_pipeline.py`

**Files:**
- Modify: `app/arrange_pipeline.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**
- Modifies: `run_arrange_pipeline` — unpacks `detect_chords`'s new
  3-tuple, builds a key signature from it, passes it to
  `build_grand_staff_score`.

- [ ] **Step 1: Update the production code**

In `app/arrange_pipeline.py`, add `key_signature_from_tonic` to the
existing `from app.notation.hand_split import ...` line, then change:

```python
        chords, seconds_per_quarter = detect_chords(str(harmony_path))
```

to:

```python
        chords, seconds_per_quarter, detected_key = detect_chords(str(harmony_path))
```

And change the score-building loop to pass the key signature:

```python
        difficulties = {}
        key_signature = key_signature_from_tonic(*detected_key)
        for tier, lh_part in (("easy", variants.easy), ("medium", variants.medium), ("hard", variants.hard)):
            score = build_grand_staff_score(rh_variants[tier], lh_part, title=title, key_signature=key_signature)
```

(The `key_signature` variable is built once, outside the loop, but
`build_grand_staff_score` deep-copies it per-part internally per Task 2
— safe to reuse the same object across all three tier calls in this
loop, since it's never mutated after construction here.)

- [ ] **Step 2: Update the test that monkeypatches `detect_chords`**

In `backend/tests/test_api.py`, update
`test_arrange_full_job_lifecycle_returns_transcribe_shaped_result`'s
`detect_chords` monkeypatch to return the new 3-tuple:

```python
    monkeypatch.setattr(
        pipeline_module, "detect_chords",
        lambda audio_path: ([ChordSymbol(start=0.0, duration=1.0, root=0, quality="major")], 0.5, (0, "major")),
    )
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -v -k arrange`
Expected: PASS (all 3 arrange tests)

- [ ] **Step 4: Run the full backend test suite**

Run: `cd backend && ./.venv/bin/python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/arrange_pipeline.py backend/tests/test_api.py
git commit -m "feat: apply the song's detected key signature to arranged output"
```

## Task 4: Verify against a real song

- [ ] **Step 1: Run the full arrange pipeline against a real song already
  on disk (if one exists) and inspect the exported MusicXML's key
  signature**

```bash
find backend/storage -name "harmony.wav" | head -1
```

From `backend/`, using the song_id from that path:

```bash
./.venv/bin/python -c "
from app.chords.detect import detect_chords
from app.notation.hand_split import key_signature_from_tonic

chords, spq, detected_key = detect_chords('storage/<song_id>/stems/harmony.wav')
k = key_signature_from_tonic(*detected_key)
print('detected key:', k.tonic.name, k.mode, '| sharps:', k.sharps)
"
```

Report the detected key and sharps count in your final summary — this is
a sanity check, not a strict pass/fail assertion.

## Out of Scope for This Plan

- Time signature — explicitly deferred (hardcoded 4/4 stays as-is).
- Careful enharmonic respelling of individual notes to match the new key
  signature (e.g. a note currently spelled A# might read more naturally
  as Bb once a flat-key signature is applied) — `simplifyEnharmonic`-style
  cleanup, if needed, is a separate follow-up once real output can be
  visually reviewed.
