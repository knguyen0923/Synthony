# Instrumental Arrangement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `/arrange`'s vocals stem yields no real melody (a genuinely instrumental song), stop silently producing a near-empty right hand. Instead, transcribe the harmony mix directly and split it into two hands via Spec 1's proven continuity-aware DP (`assign_hands`), the same machinery Spec 1 already uses for "many simultaneous voices, no predetermined melody/harmony split."

**Architecture:** One new predicate (`_is_instrumental`) and one new function (`_instrumental_variants`) added to `backend/app/arrange_pipeline.py`. No new modules, no changes to `app/notation/`, `app/melody/`, or `app/lh/` — everything the new path calls (`assign_hands`, `cap_simultaneous_notes`, `notes_to_part`, `transcribe_audio_to_notes`) already exists and is already used by at least one of the two pipelines.

**Tech Stack:** Python, music21, Basic Pitch — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-12-instrumental-arrangement-design.md` — read this first; this plan implements it task-by-task without repeating its rationale.

## Global Constraints

- The existing pop/rock path (`_rh_variants`/`_lh_variants`, unconditional today) must be byte-for-byte unaffected for any input that still produces a plausible vocal melody — this is a new branch, not a rewrite of the existing one.
- `MIN_MELODY_NOTES` is a first-pass tuning constant, expected to be adjusted after real-audio verification (Task 3) — don't treat `8` as load-bearing before that check runs.
- Follow this repo's TDD discipline: write the failing test, verify the exact failure, implement, verify green, commit — for every step below.
- Tasks 1 and 2 touch the same file (`arrange_pipeline.py`) but are logically independent (a pure predicate vs. a note-processing function) — implement Task 1 first since Task 3's routing test depends on `_is_instrumental` existing, then Task 2, then Task 3.

---

### Task 1: `_is_instrumental` predicate

**Files:**
- Modify: `backend/app/arrange_pipeline.py`
- Modify: `backend/tests/test_arrange_pipeline.py`

**Interfaces:**
- Produces (for Task 3): `MIN_MELODY_NOTES: int` (constant), `_is_instrumental(melody_notes: list[NoteEvent]) -> bool`.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_arrange_pipeline.py` (add `NoteEvent` to the existing import from `app.notation.types` if not already imported — it already is, per the file's existing tests):

```python
from app.arrange_pipeline import MIN_MELODY_NOTES, _is_instrumental


def test_is_instrumental_true_when_melody_notes_are_far_below_the_threshold():
    assert _is_instrumental([]) is True
    assert _is_instrumental([NoteEvent(start=0.0, end=0.5, pitch=60)]) is True


def test_is_instrumental_false_at_and_above_the_threshold():
    notes_at_threshold = [NoteEvent(start=float(i), end=float(i) + 0.5, pitch=60) for i in range(MIN_MELODY_NOTES)]
    assert _is_instrumental(notes_at_threshold) is False

    notes_above_threshold = notes_at_threshold + [NoteEvent(start=100.0, end=100.5, pitch=60)]
    assert _is_instrumental(notes_above_threshold) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -k is_instrumental -v`
Expected: FAIL — `ImportError: cannot import name 'MIN_MELODY_NOTES' from 'app.arrange_pipeline'`.

- [ ] **Step 3: Implement**

In `backend/app/arrange_pipeline.py`, add after the existing module-level imports (no new imports needed for this task):

```python
# A real sung melody in a full-length song produces far more than this many
# detected notes; a near-silent/noise-only vocals stem (genuinely
# instrumental input) produces far fewer. First-pass tuning constant —
# expect to adjust after real-audio verification (see the design spec).
MIN_MELODY_NOTES = 8


def _is_instrumental(melody_notes: list) -> bool:
    """True when extract_melody_notes's output is implausibly short for a
    real sung melody — treated as "no real vocal content," routing
    run_arrange_pipeline to the instrumental path instead of building RH
    from near-empty or noise-artifact notes."""
    return len(melody_notes) < MIN_MELODY_NOTES
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -k is_instrumental -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/arrange_pipeline.py backend/tests/test_arrange_pipeline.py
git commit -m "feat: add _is_instrumental predicate for the instrumental-arrangement branch"
```

---

### Task 2: `_instrumental_variants` — DP hand-split for songs with no real vocal melody

**Files:**
- Modify: `backend/app/arrange_pipeline.py`
- Modify: `backend/tests/test_arrange_pipeline.py`

**Interfaces:**
- Consumes: `assign_hands` (`app.notation.hand_assignment`), `cap_simultaneous_notes` (`app.notation.voice_cap`), `notes_to_part`, `MAX_SIMULTANEOUS_VOICES_PER_HAND` (`app.notation.hand_split`), `transcribe_audio_to_notes` (`app.transcription.audio_to_midi`), `HARD_LH_RANGE`, `LH_MINIMUM_NOTE_LENGTH_MS` (`app.lh.extract`) — all pre-existing, unchanged.
- Produces (for Task 3): `_instrumental_variants(harmony_path: str, seconds_per_quarter: float, beat_map: Optional[BeatMap] = None) -> tuple[dict, dict]` — returns `(rh_variants, lh_variants)`, each shaped exactly like `_rh_variants`/`_lh_variants`'s existing return dicts (`{"easy": Part, "medium": Part, "hard": Part}`).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_arrange_pipeline.py`:

```python
def test_instrumental_variants_splits_notes_into_both_hands_via_dp(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    # A held low note plus a held high note at the same onset -- assign_hands'
    # DP splits a lone onset by pitch when there's no established continuity
    # yet, so this should land as one RH note and one LH note.
    fake_notes = [
        NoteEvent(start=0.0, end=2.0, pitch=72, velocity=0.8),  # high
        NoteEvent(start=0.0, end=2.0, pitch=48, velocity=0.8),  # low
    ]
    monkeypatch.setattr(pipeline_module, "transcribe_audio_to_notes", lambda audio_path, minimum_note_length=None: fake_notes)

    rh_variants, lh_variants = pipeline_module._instrumental_variants("fake/harmony.wav", 0.5)

    assert set(rh_variants.keys()) == {"easy", "medium", "hard"}
    assert set(lh_variants.keys()) == {"easy", "medium", "hard"}
    rh_pitches = [n.pitch.midi for n in rh_variants["hard"].flatten().notes]
    lh_pitches = [n.pitch.midi for n in lh_variants["hard"].flatten().notes]
    assert rh_pitches == [72]
    assert lh_pitches == [48]


def test_instrumental_variants_caps_simultaneous_voices_per_hand(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    # Five simultaneous high notes: assign_hands' hard span cutoff (2
    # octaves) and RH's melody tie-break will put some/all in RH; whichever
    # hand ends up with more than MAX_SIMULTANEOUS_VOICES_PER_HAND (4) must
    # get capped by cap_simultaneous_notes.
    fake_notes = [
        NoteEvent(start=0.0, end=2.0, pitch=pitch, velocity=velocity)
        for pitch, velocity in [(60, 0.9), (62, 0.8), (64, 0.7), (65, 0.6), (67, 0.1)]
    ]
    monkeypatch.setattr(pipeline_module, "transcribe_audio_to_notes", lambda audio_path, minimum_note_length=None: fake_notes)

    rh_variants, _lh_variants = pipeline_module._instrumental_variants("fake/harmony.wav", 0.5)

    hard_notes = list(rh_variants["hard"].flatten().notes)
    assert len(hard_notes) <= 4


def test_instrumental_variants_lh_stays_in_the_hard_lh_range(monkeypatch):
    import app.arrange_pipeline as pipeline_module
    from app.lh.extract import HARD_LH_RANGE

    fake_notes = [
        NoteEvent(start=0.0, end=1.0, pitch=90, velocity=0.9),  # high -- RH by span/tiebreak
        NoteEvent(start=0.0, end=1.0, pitch=84, velocity=0.5),  # also high, but should land LH and get shifted down
    ]
    monkeypatch.setattr(pipeline_module, "transcribe_audio_to_notes", lambda audio_path, minimum_note_length=None: fake_notes)

    _rh_variants, lh_variants = pipeline_module._instrumental_variants("fake/harmony.wav", 0.5)

    lh_pitches = [n.pitch.midi for n in lh_variants["hard"].flatten().notes]
    assert all(HARD_LH_RANGE[0] <= p <= HARD_LH_RANGE[1] for p in lh_pitches)


def test_instrumental_variants_passes_minimum_note_length_to_transcription(monkeypatch):
    import app.arrange_pipeline as pipeline_module
    from app.lh.extract import LH_MINIMUM_NOTE_LENGTH_MS

    captured = {}

    def fake_transcribe(audio_path, minimum_note_length=None):
        captured["minimum_note_length"] = minimum_note_length
        return [NoteEvent(start=0.0, end=1.0, pitch=60, velocity=0.5)]

    monkeypatch.setattr(pipeline_module, "transcribe_audio_to_notes", fake_transcribe)

    pipeline_module._instrumental_variants("fake/harmony.wav", 0.5)

    assert captured["minimum_note_length"] == LH_MINIMUM_NOTE_LENGTH_MS


def test_instrumental_variants_uses_a_beat_map_instead_of_a_fixed_tempo_when_given(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    fake_notes = [NoteEvent(start=1.0, end=2.0, pitch=72, velocity=0.9)]
    monkeypatch.setattr(pipeline_module, "transcribe_audio_to_notes", lambda audio_path, minimum_note_length=None: fake_notes)

    beat_map = BeatMap([0.0, 1.0, 2.0])  # 60 BPM, unlike the 120 BPM default
    rh_variants, _lh_variants = pipeline_module._instrumental_variants("fake/harmony.wav", 0.5, beat_map=beat_map)

    rh_note = list(rh_variants["hard"].flatten().notes)[0]
    assert rh_note.offset == 1.0  # 1.0 QL, not the 2.0 QL a fixed 0.5s/quarter default would give
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -k instrumental_variants -v`
Expected: FAIL — `AttributeError: module 'app.arrange_pipeline' does not have the attribute 'transcribe_audio_to_notes'` (the function isn't imported into the module yet, so `monkeypatch.setattr` can't find it).

- [ ] **Step 3: Implement**

In `backend/app/arrange_pipeline.py`, update the existing import block:

```python
from app.difficulty.easy import EASY_GRID, EASY_LH_RANGE, EASY_RH_RANGE
from app.difficulty.medium import MAX_VOICING_TONES, MEDIUM_GRID, MEDIUM_LH_RANGE, MEDIUM_RH_RANGE
from app.difficulty.quantize import quantize_part
from app.difficulty.range_shift import shift_into_range
from app.export import export_musicxml
from app.jobs import set_failed, set_result, set_status
from app.lh.extract import HARD_LH_RANGE, LH_MINIMUM_NOTE_LENGTH_MS, build_lh_part, extract_lh_notes
from app.melody.extract import build_melody_part, extract_melody_notes
from app.notation.hand_assignment import assign_hands
from app.notation.hand_split import (
    MAX_SIMULTANEOUS_VOICES_PER_HAND,
    SECONDS_PER_QUARTER,
    build_grand_staff_score,
    key_signature_from_tonic,
    notes_to_part,
)
from app.notation.voice_cap import cap_simultaneous_notes
from app.separation.separator import separate_stems
from app.storage import evict_oldest_songs, write_metadata
from app.tempo.detect import BeatMap, detect_beat_map
from app.transcription.audio_to_midi import transcribe_audio_to_notes
```

Add, after `_lh_variants`:

```python
def _instrumental_variants(
    harmony_path: str, seconds_per_quarter: float = SECONDS_PER_QUARTER, beat_map: Optional[BeatMap] = None
):
    """RH/LH variants for a song with no real vocal melody (see
    _is_instrumental): transcribe the harmony mix directly and split it
    into hands via Spec 1's continuity-aware DP (assign_hands) instead of
    Spec 2's usual vocals-are-RH/bass+other-are-LH fixed roles. Mirrors
    _rh_variants/_lh_variants' shape exactly so downstream tier derivation
    and build_grand_staff_score's per-tier loop are unaffected."""
    notes = transcribe_audio_to_notes(harmony_path, minimum_note_length=LH_MINIMUM_NOTE_LENGTH_MS)
    rh_notes, lh_notes = assign_hands(notes)
    rh_notes = cap_simultaneous_notes(rh_notes, MAX_SIMULTANEOUS_VOICES_PER_HAND)
    lh_notes = cap_simultaneous_notes(lh_notes, MAX_SIMULTANEOUS_VOICES_PER_HAND)

    rh_base = notes_to_part(rh_notes, part_id="RH", seconds_per_quarter=seconds_per_quarter, beat_map=beat_map)
    lh_base = shift_into_range(
        notes_to_part(lh_notes, part_id="LH", seconds_per_quarter=seconds_per_quarter, beat_map=beat_map),
        *HARD_LH_RANGE,
    )

    rh_variants = {
        "easy": shift_into_range(quantize_part(rh_base, EASY_GRID), *EASY_RH_RANGE),
        "medium": shift_into_range(quantize_part(rh_base, MEDIUM_GRID), *MEDIUM_RH_RANGE),
        "hard": rh_base,
    }
    lh_variants = {
        "easy": shift_into_range(quantize_part(lh_base, EASY_GRID, max_voices=1), *EASY_LH_RANGE),
        "medium": shift_into_range(quantize_part(lh_base, MEDIUM_GRID, max_voices=MAX_VOICING_TONES), *MEDIUM_LH_RANGE),
        "hard": lh_base,
    }
    return rh_variants, lh_variants
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_arrange_pipeline.py -k instrumental_variants -v`
Expected: PASS (all 5 tests). If `test_instrumental_variants_splits_notes_into_both_hands_via_dp` fails because `assign_hands` assigned both notes to the same hand instead of splitting a lone two-note onset by pitch, re-check that test's assumption against `assign_hands`'s actual current tie-break behavior (its docstring in `app/notation/hand_assignment.py` documents the exact rule) rather than adjusting the implementation to force a specific split — this test exists to document real DP behavior, not to assert a behavior `_instrumental_variants` itself controls.

- [ ] **Step 5: Run the full backend suite as a regression check**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS. `_instrumental_variants` isn't called from anywhere yet (that's Task 3), so nothing else should be affected.

- [ ] **Step 6: Commit**

```bash
git add backend/app/arrange_pipeline.py backend/tests/test_arrange_pipeline.py
git commit -m "feat: add _instrumental_variants — DP hand-split for songs with no real vocal melody"
```

---

### Task 3: Wire the branch into `run_arrange_pipeline`, verify end-to-end

**Depends on:** Tasks 1 and 2 complete.

**Files:**
- Modify: `backend/app/arrange_pipeline.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:** No new public interface — this task only changes `run_arrange_pipeline`'s internal control flow.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_api.py`, near the existing `test_arrange_full_job_lifecycle_returns_transcribe_shaped_result` test. This file has no shared polling helper — every arrange test inlines the same poll loop (see that existing test) and reads `"song_id" in payload or payload.get("status") == "failed"` as the done-condition (there's no top-level `"status": "done"` field on success). Add `from music21 import note, stream` alongside this file's existing `import time` / `NoteEvent` / `Stems` / `BeatMap` imports (all already present just above `test_arrange_full_job_lifecycle_returns_transcribe_shaped_result`), then add:

```python
def test_arrange_routes_to_instrumental_path_when_no_real_melody_detected(monkeypatch, synthetic_piano_wav):
    import app.arrange_pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=Path("/fake/vocals.wav"), drums=Path("/fake/drums.wav"),
            bass=Path("/fake/bass.wav"), other=Path("/fake/other.wav"),
        ),
    )
    monkeypatch.setattr(pipeline_module, "mix_wav_files", lambda a, b, dest: dest)
    # Fewer than MIN_MELODY_NOTES -- must route to _instrumental_variants.
    monkeypatch.setattr(pipeline_module, "extract_melody_notes", lambda audio_path: [NoteEvent(start=0.0, end=0.5, pitch=60)])
    monkeypatch.setattr(pipeline_module, "detect_key_and_tempo", lambda audio_path: ((0, "major"), 0.5))
    monkeypatch.setattr(pipeline_module, "detect_beat_map", lambda audio_path: BeatMap.constant(0.5))

    instrumental_called = {}

    def fake_instrumental_variants(harmony_path, seconds_per_quarter, beat_map=None):
        instrumental_called["called"] = True
        rh_part = stream.Part(id="RH")
        rh_part.insert(0.0, note.Note("C4"))
        lh_part = stream.Part(id="LH")
        lh_part.insert(0.0, note.Note("C3"))
        return (
            {"easy": rh_part, "medium": rh_part, "hard": rh_part},
            {"easy": lh_part, "medium": lh_part, "hard": lh_part},
        )

    monkeypatch.setattr(pipeline_module, "_instrumental_variants", fake_instrumental_variants)

    def boom_if_called(*args, **kwargs):
        raise AssertionError("_rh_variants/_lh_variants must not run on the instrumental path")

    monkeypatch.setattr(pipeline_module, "_rh_variants", boom_if_called)
    monkeypatch.setattr(pipeline_module, "_lh_variants", boom_if_called)

    with open(synthetic_piano_wav, "rb") as f:
        response = client.post("/arrange", files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")})
    job_id = response.json()["job_id"]

    result = None
    for _ in range(50):
        payload = client.get(f"/arrange/{job_id}").json()
        if "song_id" in payload or payload.get("status") == "failed":
            result = payload
            break
        time.sleep(0.05)

    assert result is not None, "job did not complete in time"
    assert instrumental_called.get("called") is True
    assert "song_id" in result, f"job failed instead of completing: {result}"


def test_arrange_does_not_route_to_instrumental_path_with_a_real_melody(monkeypatch, synthetic_piano_wav):
    import app.arrange_pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=Path("/fake/vocals.wav"), drums=Path("/fake/drums.wav"),
            bass=Path("/fake/bass.wav"), other=Path("/fake/other.wav"),
        ),
    )
    monkeypatch.setattr(pipeline_module, "mix_wav_files", lambda a, b, dest: dest)
    # At/above MIN_MELODY_NOTES -- must stay on the existing path, unaffected.
    plenty_of_notes = [NoteEvent(start=float(i), end=float(i) + 0.5, pitch=72) for i in range(pipeline_module.MIN_MELODY_NOTES)]
    monkeypatch.setattr(pipeline_module, "extract_melody_notes", lambda audio_path: plenty_of_notes)
    monkeypatch.setattr(pipeline_module, "extract_lh_notes", lambda audio_path: [NoteEvent(start=0.0, end=0.5, pitch=48)])
    monkeypatch.setattr(pipeline_module, "detect_key_and_tempo", lambda audio_path: ((0, "major"), 0.5))
    monkeypatch.setattr(pipeline_module, "detect_beat_map", lambda audio_path: BeatMap.constant(0.5))

    def boom_if_called(*args, **kwargs):
        raise AssertionError("_instrumental_variants must not run when a real melody was detected")

    monkeypatch.setattr(pipeline_module, "_instrumental_variants", boom_if_called)

    with open(synthetic_piano_wav, "rb") as f:
        response = client.post("/arrange", files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")})
    job_id = response.json()["job_id"]

    result = None
    for _ in range(50):
        payload = client.get(f"/arrange/{job_id}").json()
        if "song_id" in payload or payload.get("status") == "failed":
            result = payload
            break
        time.sleep(0.05)

    assert result is not None, "job did not complete in time"
    assert "song_id" in result, f"job failed instead of completing: {result}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k "instrumental_path or does_not_route" -v`
Expected: FAIL on the first test — `instrumental_called.get("called")` is `None` (`_instrumental_variants` exists as a function since Task 2, but `run_arrange_pipeline` doesn't call it yet, so the monkeypatched version never runs). The second test currently passes already (nothing calls `_instrumental_variants` yet) — that's fine, it becomes a real regression check once Step 3 below lands.

- [ ] **Step 3: Wire the branch into `run_arrange_pipeline`**

In `backend/app/arrange_pipeline.py`, replace:

```python
            set_status(job_id, "arranging")
            lh_variants = _lh_variants(str(harmony_path), seconds_per_quarter, beat_map)
            rh_variants = _rh_variants(melody_notes, seconds_per_quarter, beat_map)
```

with:

```python
            set_status(job_id, "arranging")
            if _is_instrumental(melody_notes):
                logger.info("job %s: no real vocal melody detected, using DP hand-split", job_id)
                rh_variants, lh_variants = _instrumental_variants(str(harmony_path), seconds_per_quarter, beat_map)
            else:
                lh_variants = _lh_variants(str(harmony_path), seconds_per_quarter, beat_map)
                rh_variants = _rh_variants(melody_notes, seconds_per_quarter, beat_map)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_api.py -k "instrumental_path or does_not_route" -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS, zero failures, zero collection errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/arrange_pipeline.py backend/tests/test_api.py
git commit -m "feat: route /arrange to the DP hand-split path when no real vocal melody is detected"
```

- [ ] **Step 7: Real-audio verification (mandatory — this is the load-bearing check for this whole plan)**

Per this project's established real-audio verification workflow, and its stated preference to scope real-song *listening* checks to the **Hard tier only**:

1. Start the local backend: `cd backend && ./.venv/bin/python -m uvicorn app.main:app --port 8000`.
2. Submit the existing 3-song pop/rock real-audio corpus through `/arrange` (paths from the most recent verification run). Confirm each still completes normally and does **not** trigger the instrumental branch — spot-check via the server log line added in Step 3 (`"no real vocal melody detected"` must NOT appear for any of these three).
3. Submit at least one genuinely instrumental real song (no vocals at all) through `/arrange`. Confirm the log line above **does** appear, and the job completes successfully.
4. Convert each result's Hard-tier MusicXML to MIDI (`music21.converter.parse(...).write("midi", ...)`) and listen. Judge specifically: does the DP-split RH/LH sound like a reasonable two-hand instrumental arrangement (not silence, not one hand doing everything, not a nonsensical register split) — this is the open risk flagged in the spec (`assign_hands`'s tuning was validated against solo piano audio, not a multi-instrument harmony mix, so this is genuinely new territory for it).
5. If `MIN_MELODY_NOTES` misfires in either direction (a real pop/rock song's vocals stem yields fewer than 8 notes, or a genuinely instrumental track's near-silent vocals stem yields 8+ noise-artifact notes), that's expected first-pass tuning territory per the spec — adjust the constant in `backend/app/arrange_pipeline.py` and re-verify, don't silently ship a misfiring threshold.
6. If the DP-split output sounds musically unreasonable in a way that isn't a simple constant tweak, report the finding rather than attempting a deeper fix in this pass — per the spec's "Open risk" section, this may need its own follow-up investigation (e.g. `assign_hands`'s piano-specific tuning constants may need revisiting for non-piano input), not a same-pass patch.

---

## Deferred (per the design spec, not in scope here)

- Orchestral, rap, and true multi-melody support — explicitly separate specs per the Track 3 research findings.
- Any onset-cleanup/legato pass for the DP-split RH/LH output (only add one if Step 7's listening surfaces fragmented onsets as an actual problem).
- Revisiting `assign_hands`'s tuning constants for non-piano input, unless Step 7's listening shows a real problem (see the spec's "Open risk" section).
