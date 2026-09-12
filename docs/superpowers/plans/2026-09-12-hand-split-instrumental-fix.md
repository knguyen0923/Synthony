# Hand-Split Multi-Instrument Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `assign_hands`'s lone-note-always-RH special case so it no longer forces a badly unbalanced hand split on multi-instrument (non-piano) input, without regressing its existing, real-audio-validated behavior on solo piano input.

**Architecture:** Remove the unconditional `n == 1: masks = [(True,)]` bypass in `assign_hands` (`backend/app/notation/hand_assignment.py`). Replace it with a per-particle gate: once *both* hands already have an established pitch centroid, let a lone note flow through the same `_legal_masks`/`_score_mask` DP path as every other onset size (with a small RH tie-break bias added in `_score_mask`); until then (cold start — either hand never yet used), keep the original hard bypass exactly as-is. This preserves every existing test unchanged (verified empirically below) while letting real continuity signal correctly route lone bass/chord notes to LH once the piece has established both hands' registers — which is the actual multi-instrument failure mode.

**Tech Stack:** Python 3.11, pytest, FastAPI backend (`backend/app/`), the existing `backend/scripts/quality_harness/` real-audio harness (music21-based MusicXML metrics + MIDI export).

**Spec:** `docs/superpowers/specs/2026-09-12-hand-split-instrumental-fix-design.md`

**Note on the spec's exact mechanism:** while writing this plan, pre-implementation verification (prototyped directly against the real module, run against the full existing test suite, then reverted — see Task 1) found that the spec's originally-described "flat RH bias competing with existing costs" needed one refinement to avoid a real regression: gating DP-scoring of lone notes on *both* hands already being established, not applying it unconditionally. Without this gate, a large register jump at a moment when one hand has literally never been used defeats any bias small enough to still fix the real bug (a never-used hand's `NEW_HAND_COST == 0.0` makes it deceptively "free" to grab, regardless of the bias) — this is exactly the failure mode `test_sustained_low_melody_run_stays_in_right_hand` guards against, and it goes red without the gate. With the gate, that test (and all 46 existing tests in `test_hand_assignment.py`/`test_hand_split.py`) passes unchanged, and the multi-instrument scenario the fix targets still routes correctly to LH. This refinement is additive to the spec's design, not a different approach — Task 1 below re-derives it via proper TDD so the change lands through the normal failing-test-first workflow, not by copying the prototype.

## Global Constraints

- Real-audio verification is mandatory before this plan is considered done (project-wide norm) — Task 4 covers it, scoped to Hard tier listening only, per this project's standing preference.
- TDD is non-negotiable for backend Python work in this repo — every code change task below writes the failing test first.
- Run the full backend suite (`cd backend && ./.venv/bin/python -m pytest -v`) before any commit that touches shared code.
- No absolute-pitch threshold may be introduced anywhere in `hand_assignment.py` (existing module design principle — see its docstring) — this plan's fix uses only relative/continuity-based signal plus the existing gating condition, never a raw pitch cutoff.

---

## File Structure

- **Modify:** `backend/app/notation/hand_assignment.py` — the core fix (Task 2).
- **Modify:** `backend/tests/test_hand_assignment.py` — new regression test for the multi-instrument scenario (Task 2).
- **Create:** `backend/scripts/diagnose_onset_grouping.py` — standalone diagnostic script, reusing production transcription/separation functions directly (no HTTP), to rule the onset-grouping tolerance factor in or out (Task 1).
- **Modify (conditionally):** `backend/app/notation/hand_assignment.py`'s `_group_by_onset` — only if Task 1's diagnostic finds onset mis-grouping material (Task 1's own branch instructions cover this; no separate task number, since whether it runs at all is decided by Task 1's own output).
- **Modify:** `backend/scripts/quality_harness/run_baseline.py` — add the rock-instrumental asset as a permanent `Source` entry so it participates in the harness's before/after workflow (Task 4).

No new modules. This stays a small, targeted fix to one existing function plus its test file, plus one new standalone diagnostic script (not part of the pytest suite — it's a one-time investigation tool, following the `backend/scripts/quality_harness/` precedent for standalone real-audio scripts).

---

### Task 1: Onset-grouping diagnostic

**Files:**
- Create: `backend/scripts/diagnose_onset_grouping.py`

**Interfaces:**
- Consumes: `app.separation.separator.separate_stems(audio_path: str, output_dir: Path) -> Stems` (returns a `Stems` dataclass with `.bass`/`.other`/`.vocals`/`.drums` `Path` attributes); `app.arrange_pipeline.mix_wav_files(path_a: Path, path_b: Path, dest: Path) -> Path`; `app.lh.extract.LH_MINIMUM_NOTE_LENGTH_MS` (currently `180`); `app.transcription.audio_to_midi.transcribe_audio_to_notes(audio_path: str, minimum_note_length: Optional[float] = None) -> list[NoteEvent]`; `app.notation.hand_assignment._group_by_onset(notes: list[NoteEvent]) -> list[list[NoteEvent]]`.
- Produces: a printed report (see Step 2) and a go/no-go decision that determines whether the follow-up merge-window sub-task (documented inline in Step 3) runs at all. Nothing else in this plan depends on this script's code, only on its printed decision.

This step is diagnostic, not TDD (there's no "failing test" for an investigation script) — it's a one-time real-audio measurement.

- [ ] **Step 1: Write the diagnostic script**

```python
#!/usr/bin/env python3
"""One-time diagnostic: measure whether onset-grouping tolerance
(ONSET_ROUND_DECIMALS in app.notation.hand_assignment) is a material
contributor to assign_hands's lone-note-onset rate on real multi-instrument
input, or whether that rate is simply genuine (bass/chord tones landing on
truly distinct onsets). See docs/superpowers/specs/
2026-09-12-hand-split-instrumental-fix-design.md's "Diagnostic" section.

Reproduces exactly what app.arrange_pipeline._instrumental_variants does to
get from a raw audio file to the note list assign_hands receives (stem
separation -> bass+other mix -> transcription), then measures onset-group
sizes and near-miss merges on that note list. Does not call assign_hands
itself -- this only inspects _group_by_onset's output.

USAGE
  cd backend
  ./.venv/bin/python scripts/diagnose_onset_grouping.py \
      scripts/quality_harness/assets/arrange_instrumental_big_rock.mp3
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.arrange_pipeline import mix_wav_files  # noqa: E402
from app.lh.extract import LH_MINIMUM_NOTE_LENGTH_MS  # noqa: E402
from app.notation.hand_assignment import _group_by_onset  # noqa: E402
from app.separation.separator import separate_stems  # noqa: E402
from app.transcription.audio_to_midi import transcribe_audio_to_notes  # noqa: E402

# A near-miss merge window: two onsets this close together are the kind of
# timing jitter Basic Pitch/Demucs could plausibly produce for notes meant
# to sound together, distinct from a genuinely separate musical event.
# 30ms is comfortably larger than typical onset-detection jitter and
# comfortably smaller than the shortest notes this pipeline's minimum note
# length (180ms) would ever produce.
MERGE_WINDOW_SECONDS = 0.03

# Below this fraction of lone-note onsets being near-miss-mergeable, onset
# grouping is ruled out as a material contributor (the observed lone-note
# rate is mostly genuine, not a grouping artifact).
MATERIAL_THRESHOLD = 0.15


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <audio_path>")
        return 1
    audio_path = sys.argv[1]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        print(f"Separating stems for {audio_path} ...")
        stems = separate_stems(audio_path, tmp_dir / "stems")
        harmony_path = mix_wav_files(stems.bass, stems.other, tmp_dir / "harmony.wav")

        print("Transcribing harmony mix ...")
        notes = transcribe_audio_to_notes(str(harmony_path), minimum_note_length=LH_MINIMUM_NOTE_LENGTH_MS)

    groups = _group_by_onset(notes)
    total_groups = len(groups)
    size_1_groups = [(i, g) for i, g in enumerate(groups) if len(g) == 1]

    mergeable = 0
    for i, group in size_1_groups:
        if i + 1 >= len(groups):
            continue
        next_group = groups[i + 1]
        this_onset = group[0].start
        next_onset = next_group[0].start
        if next_onset - this_onset <= MERGE_WINDOW_SECONDS:
            mergeable += 1

    fraction_size_1 = len(size_1_groups) / total_groups if total_groups else 0.0
    fraction_mergeable = mergeable / len(size_1_groups) if size_1_groups else 0.0

    print(f"Total onset groups: {total_groups}")
    print(f"Size-1 (lone-note) groups: {len(size_1_groups)} ({fraction_size_1:.1%} of all groups)")
    print(f"Of those, within {MERGE_WINDOW_SECONDS * 1000:.0f}ms of the next onset: "
          f"{mergeable} ({fraction_mergeable:.1%} of size-1 groups)")

    if fraction_mergeable >= MATERIAL_THRESHOLD:
        print(f"MATERIAL (>= {MATERIAL_THRESHOLD:.0%}): onset-grouping tolerance is a real contributor. "
              "Implement the ONSET_MERGE_WINDOW_SECONDS follow-up described in Task 1's Step 3 "
              "before proceeding to Task 2.")
    else:
        print(f"RULED OUT (< {MATERIAL_THRESHOLD:.0%}): the lone-note rate is mostly genuine, "
              "not a grouping artifact. Proceed directly to Task 2; no change to _group_by_onset needed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it against the real instrumental track and record the result**

Run:
```bash
cd backend
./.venv/bin/python scripts/diagnose_onset_grouping.py scripts/quality_harness/assets/arrange_instrumental_big_rock.mp3
```

Expected: prints the report above and one of the two concluding lines (`MATERIAL` or `RULED OUT`). This will take a few minutes (Demucs stem separation + Basic Pitch transcription on a full song).

- [ ] **Step 3: Branch on the result**

**If `RULED OUT`:** do nothing further to `_group_by_onset`. Record the finding as a one-line addendum to the design spec's "Diagnostic" section (`docs/superpowers/specs/2026-09-12-hand-split-instrumental-fix-design.md`): replace its "Go/no-go" paragraph's forward-looking wording with the actual measured percentages and "ruled out." Commit this spec update alongside Task 1's script (Step 4 below covers the commit). Proceed to Task 2.

**If `MATERIAL`:** implement this fix in `backend/app/notation/hand_assignment.py`, then re-run the diagnostic script to confirm the mergeable fraction has dropped, following the same TDD discipline as Task 2 (write the failing test first):

First, the failing test in `backend/tests/test_hand_assignment.py`:
```python
def test_near_onset_notes_within_the_merge_window_are_grouped_together():
    """Two notes 20ms apart (well inside the merge window, well outside
    normal onset-rounding at ONSET_ROUND_DECIMALS=3) must be treated as one
    onset group, not two separate lone-note groups."""
    from app.notation.hand_assignment import _group_by_onset

    notes = [
        NoteEvent(start=0.000, end=0.5, pitch=40),
        NoteEvent(start=0.020, end=0.5, pitch=64),
    ]
    groups = _group_by_onset(notes)
    assert len(groups) == 1
    assert {n.pitch for n in groups[0]} == {40, 64}


def test_onsets_further_apart_than_the_merge_window_stay_separate():
    from app.notation.hand_assignment import _group_by_onset

    notes = [
        NoteEvent(start=0.000, end=0.5, pitch=40),
        NoteEvent(start=0.100, end=0.5, pitch=64),
    ]
    groups = _group_by_onset(notes)
    assert len(groups) == 2
```

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_hand_assignment.py -k merge_window -v`
Expected: FAIL (both notes currently land in separate groups regardless of gap, since `_group_by_onset` only rounds to `ONSET_ROUND_DECIMALS`, it doesn't merge).

Then implement, in `backend/app/notation/hand_assignment.py`:
```python
# A second onset within this many seconds of the first is merged into the
# same DP onset group, on top of the ONSET_ROUND_DECIMALS rounding above.
# Only added if the diagnostic script (scripts/diagnose_onset_grouping.py)
# found a material fraction of lone-note onsets on real multi-instrument
# input were within this window of their neighbor -- see that script's
# MERGE_WINDOW_SECONDS constant, which this must match.
ONSET_MERGE_WINDOW_SECONDS = 0.03


def _group_by_onset(notes: list[NoteEvent]) -> list[list[NoteEvent]]:
    by_onset: dict[float, list[NoteEvent]] = {}
    for event in notes:
        by_onset.setdefault(round(event.start, ONSET_ROUND_DECIMALS), []).append(event)
    onsets = sorted(by_onset)

    merged: list[list[NoteEvent]] = []
    for onset in onsets:
        if merged and onset - merged[-1][0].start <= ONSET_MERGE_WINDOW_SECONDS:
            merged[-1].extend(by_onset[onset])
        else:
            merged.append(list(by_onset[onset]))
    return merged
```

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_hand_assignment.py -k merge_window -v`
Expected: PASS.

Run the full suite to check nothing else regressed: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: all pass (this change only widens which onsets get grouped together; it does not change `_score_mask`/`_legal_masks` at all, so any regression here means the merge window is too wide — if so, lower `ONSET_MERGE_WINDOW_SECONDS`, re-run, and re-check the diagnostic script's own numbers still show improvement before proceeding).

- [ ] **Step 4: Commit**

```bash
cd /Users/knguyen/VSC/Synthony
git add backend/scripts/diagnose_onset_grouping.py docs/superpowers/specs/2026-09-12-hand-split-instrumental-fix-design.md
# if Step 3 found MATERIAL and implemented the merge window, also:
# git add backend/app/notation/hand_assignment.py backend/tests/test_hand_assignment.py
git commit -m "$(cat <<'EOF'
feat: add onset-grouping diagnostic for multi-instrument hand-split

Investigates whether ONSET_ROUND_DECIMALS's tolerance is inflating the
lone-note-onset rate on real multi-instrument input, per the deferred
follow-up from Track 3 Phase 1. Records the measured result either way.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Remove the lone-note RH bypass, gate on both-hands-established

**Files:**
- Modify: `backend/app/notation/hand_assignment.py:105-111` (add constant), `:211-266` (`assign_hands`), `_score_mask` (`:161-208`)
- Test: `backend/tests/test_hand_assignment.py`

**Interfaces:**
- Consumes: `_legal_masks(group: list[NoteEvent]) -> list[tuple[bool, ...]]` (unchanged signature), `_score_mask(particle: _Particle, group: list[NoteEvent], mask: tuple[bool, ...]) -> tuple[float, Optional[float], Optional[float]]` (unchanged signature, new cost term added internally), `_Particle.rh_centroid`/`.lh_centroid: Optional[float]` (existing fields, now read inside `assign_hands`'s loop, not just inside `_score_mask`).
- Produces: `assign_hands(notes: list[NoteEvent]) -> tuple[list[NoteEvent], list[NoteEvent]]` — same signature and return shape as before; both existing call sites (`backend/app/notation/hand_split.py:255`, `backend/app/arrange_pipeline.py:120`) need no changes.

This exact change was empirically verified against the real module before writing this plan (all 46 existing tests in `test_hand_assignment.py` + `test_hand_split.py` pass unchanged, plus the target multi-instrument scenario correctly routes to LH) and then reverted, so these steps re-derive it properly through TDD.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_hand_assignment.py`:

```python
def test_lone_low_notes_route_to_lh_once_both_hands_are_established():
    """The core multi-instrument-input fix: once both hands already have a
    real pitch history (unlike a fresh piece), a lone low-register note
    whose pitch and continuity clearly belong with LH must route there,
    not be forced into RH by the old unconditional bypass. Mirrors the
    real failure this fix targets (Track 3 Phase 1 real-audio finding:
    RH 1169/LH 29 notes on a real full-band rock instrumental)."""
    notes = [
        # Establishes RH centroid=65, LH centroid=40 in one onset.
        NoteEvent(start=0.0, end=0.5, pitch=65),
        NoteEvent(start=0.0, end=0.5, pitch=40),
    ]
    for i, p in enumerate([42, 43, 41, 44, 38], start=1):
        notes.append(NoteEvent(start=i * 0.5, end=i * 0.5 + 0.5, pitch=p))

    rh, lh = assign_hands(notes)

    assert [n.pitch for n in rh] == [65]
    assert [n.pitch for n in lh] == [40, 42, 43, 41, 44, 38]
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_hand_assignment.py -k both_hands_are_established -v`
Expected: FAIL — every one of `[42, 43, 41, 44, 38]` currently lands in `rh`, not `lh` (the unconditional bypass forces every lone note to RH regardless of established centroids).

- [ ] **Step 3: Implement — add the tie-break constant**

In `backend/app/notation/hand_assignment.py`, right after `RH_MELODY_TIEBREAK_WEIGHT = 0.01` (currently line 111):

```python
# Tie-break only, for lone notes once both hands are established (see
# assign_hands): a very small nudge back toward RH when the DP's real
# continuity/switch signal is otherwise near-ambiguous, matching this
# module's existing RH-leaning convention for genuine ties. Verified
# empirically to never override a real continuity/switch signal in either
# direction -- CONTINUITY_WEIGHT and SWITCH_PENALTY are both >= 4.0x this
# value, so any real pitch/continuity difference still decides the split.
LONE_NOTE_RH_BIAS = 0.5
```

- [ ] **Step 4: Implement — add the cost term in `_score_mask`**

In `_score_mask` (`backend/app/notation/hand_assignment.py`), change:

```python
    if len(rh_notes) > 1:
        cost += RH_MELODY_TIEBREAK_WEIGHT * len(rh_notes)

    return cost, new_rh_centroid, new_lh_centroid
```

to:

```python
    if len(rh_notes) > 1:
        cost += RH_MELODY_TIEBREAK_WEIGHT * len(rh_notes)

    if len(group) == 1 and lh_notes:
        cost += LONE_NOTE_RH_BIAS

    return cost, new_rh_centroid, new_lh_centroid
```

- [ ] **Step 5: Implement — gate the mask selection in `assign_hands`**

In `assign_hands` (`backend/app/notation/hand_assignment.py`), change:

```python
    for group in groups:
        n = len(group)
        if n == 1:
            masks = [(True,)]
        elif n > MAX_GROUP_SIZE_FOR_DP:
            top_idx = max(range(n), key=lambda i: group[i].pitch)
            masks = [tuple(i == top_idx for i in range(n))]
        else:
            masks = _legal_masks(group)

        new_particles = []
        for particle in particles:
            for mask in masks:
```

to:

```python
    for group in groups:
        n = len(group)
        if n > MAX_GROUP_SIZE_FOR_DP:
            top_idx = max(range(n), key=lambda i: group[i].pitch)
            fixed_masks = [tuple(i == top_idx for i in range(n))]
        elif n > 1:
            fixed_masks = _legal_masks(group)
        else:
            fixed_masks = None  # n == 1: decided per-particle below, since
            # it depends on each particle's own centroid history.

        new_particles = []
        for particle in particles:
            if fixed_masks is not None:
                masks = fixed_masks
            elif particle.rh_centroid is not None and particle.lh_centroid is not None:
                # Both hands already established: let the DP weigh this
                # lone note on its real merits instead of forcing RH.
                masks = _legal_masks(group)
            else:
                # Cold start (one or both hands never used yet): preserve
                # the original convention exactly. A never-used hand's
                # NEW_HAND_COST == 0.0 would otherwise make an arbitrary
                # register jump look deceptively cheap the instant either
                # hand is still unused -- this is what
                # test_sustained_low_melody_run_stays_in_right_hand guards
                # against.
                masks = [(True,)]
            for mask in masks:
```

- [ ] **Step 6: Run the new test, verify it passes**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_hand_assignment.py -k both_hands_are_established -v`
Expected: PASS.

- [ ] **Step 7: Run the full existing regression suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_hand_assignment.py tests/test_hand_split.py tests/test_arrange_pipeline.py -v`
Expected: all pass, including every preserved-behavior test (`test_lone_low_note_is_melody_and_goes_to_right_hand`, `test_sustained_low_melody_run_stays_in_right_hand`, `test_highest_simultaneous_note_is_melody_rest_are_accompaniment`, the flicker tests). If any fail, do not change their assertions — the gate above was specifically designed and pre-verified to keep them green; a failure means Steps 3-5 were transcribed differently than verified. Re-check against this plan's exact code before adjusting `LONE_NOTE_RH_BIAS`.

- [ ] **Step 8: Run the full backend suite**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS, zero failures, zero collection errors.

- [ ] **Step 9: Commit**

```bash
cd /Users/knguyen/VSC/Synthony
git add backend/app/notation/hand_assignment.py backend/tests/test_hand_assignment.py
git commit -m "$(cat <<'EOF'
fix: route lone notes through DP scoring once both hands are established

assign_hands forced every lone-onset note to RH unconditionally, which is
right for solo piano (rare, genuinely melodic lone notes) but wrong for
multi-instrument input where bass/chord tones land on distinct onsets
constantly -- this defaulted nearly everything to RH on real instrumental
audio (Track 3 Phase 1 finding: RH 1169/LH 29 notes on a real full-band
rock instrumental). Once both hands already have continuity history, let
the existing DP cost machinery decide instead of hard-forcing RH; keep the
original bypass for the cold-start case, since a never-used hand's zero
first-use cost would otherwise make any big register jump look artificially
cheap the moment either hand is still idle.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Confirm indirect callers still behave correctly (no code changes expected)

**Files:**
- Test: `backend/tests/test_arrange_pipeline.py`, `backend/tests/test_hand_split.py` (read-only for this task — confirming, not modifying)

**Interfaces:**
- Consumes: nothing new — this task is verification only.
- Produces: nothing new — a clean test run is this task's only deliverable.

Both call sites (`hand_split.py:255`'s `notes_to_grand_staff`, `arrange_pipeline.py:120`'s `_instrumental_variants`) call `assign_hands(notes)` with an unchanged signature, so no call-site code should need to change. This task exists to make that explicit and catch it early if wrong, before the (slow) real-audio verification in Task 4.

- [ ] **Step 1: Run the full backend suite once more, standalone**

Run: `cd backend && ./.venv/bin/python -m pytest -v`
Expected: PASS, zero failures. (Same command as Task 2 Step 8 — run again here as this task's own explicit checkpoint, since Task 2's commit is the natural place to stop-and-look before moving to the slow real-audio task.)

- [ ] **Step 2: No commit needed**

This task makes no code changes. If Step 1 fails, return to Task 2 — do not patch `arrange_pipeline.py` or `hand_split.py` to work around it, since neither should need to change.

---

### Task 4: Real-audio verification (mandatory — this is the load-bearing check for this whole plan)

**Files:**
- Modify: `backend/scripts/quality_harness/run_baseline.py`

**Interfaces:**
- Consumes: `Source` dataclass (already defined in `run_baseline.py`: `name: str`, `pipeline: str`, `audio_path: Optional[Path] = None`, `youtube_url: Optional[str] = None`, `note: str = ""`), `ASSETS_DIR` (already defined, points to `backend/scripts/quality_harness/assets/`).
- Produces: `output/<label>/arrange_instrumental_big_rock/{easy,medium,hard}.musicxml` + `.mid`, plus a Downloads copy per the harness's existing behavior — this task's own verification reads from these.

- [ ] **Step 1: Add the rock-instrumental asset to the harness's fixed corpus**

In `backend/scripts/quality_harness/run_baseline.py`, add to the `SOURCES` list (after the existing `arrange_song_C` entry):

```python
    Source(
        name="arrange_instrumental_big_rock",
        pipeline="arrange",
        audio_path=ASSETS_DIR / "arrange_instrumental_big_rock.mp3",
        note=(
            "Real full-band rock instrumental (no vocals). This is the exact "
            "track whose real-audio verification during Track 3 Phase 1 "
            "found assign_hands's badly unbalanced hand split (RH 1169/LH 29 "
            "notes, 83% of RH bass-register) that this plan fixes -- kept in "
            "the fixed corpus going forward as this fix's regression check."
        ),
    ),
```

- [ ] **Step 2: Start the local backend and run the harness against both relevant sources**

Per this project's established real-audio verification workflow, scoped to **Hard tier listening only**:

```bash
cd backend/scripts/quality_harness
../../.venv/bin/python run_baseline.py --label after-hand-split-fix --only transcribe_moonlight_sonata,arrange_instrumental_big_rock
```

Expected: both sources complete with `status: ok`; console output prints each tier's total note count for both sources.

- [ ] **Step 3: Check the objective metrics for the rock instrumental**

Read `output/after-hand-split-fix/arrange_instrumental_big_rock/hard.musicxml`'s corresponding entry — either re-open the console output from Step 2, or inspect `output/after-hand-split-fix/` directly with:

```bash
cd backend/scripts/quality_harness
../../.venv/bin/python -c "
import json
from pathlib import Path
from metrics import analyze_musicxml
m = analyze_musicxml(Path('output/after-hand-split-fix/arrange_instrumental_big_rock/hard.musicxml'))
for name, part in m['parts'].items():
    print(name, 'notes:', part['note_count'], 'range:', part['pitch_range'])
"
```

Expected, compared to the pre-fix numbers documented in the spec (RH 1169 / LH 29, 83% of RH below MIDI 48): LH's note count should now be a substantial fraction of the total (not a token handful), and RH's pitch range should no longer be dominated by bass-register content. This is the load-bearing check — if LH is still near-empty or all-one-pitch, the fix did not resolve the real failure and Task 2 needs revisiting (do not tune `LONE_NOTE_RH_BIAS` blindly; re-examine whether the gate condition is actually being reached on this real input — e.g. add a temporary print of how often `masks = _legal_masks(group)` is chosen vs. the cold-start branch, using this same audio, before changing constants).

- [ ] **Step 4: Listen to the Hard-tier MIDI for both sources**

The harness already exported `.mid` files to `~/Downloads/synthony-arrangements/` (per its existing behavior) named `arrange_instrumental_big_rock-hard-after-hand-split-fix.mid` and `transcribe_moonlight_sonata-hard-after-hand-split-fix.mid`. Listen to both:

- **Rock instrumental:** does the RH/LH split now sound like a reasonable two-hand instrumental arrangement — not silence in either hand, not one hand doing everything, not a nonsensical register split?
- **Moonlight Sonata (piano):** does it still sound correct — no audible regression versus what this project's existing real-audio-validated behavior for solo piano input should sound like?

- [ ] **Step 5: Delete the listening-export files once judged**

Per this project's standing practice, delete the round's MIDI exports from `~/Downloads/synthony-arrangements/` once you've reached a verdict (accept or reject) — don't let them accumulate.

```bash
rm ~/Downloads/synthony-arrangements/arrange_instrumental_big_rock-hard-after-hand-split-fix.mid
rm ~/Downloads/synthony-arrangements/transcribe_moonlight_sonata-hard-after-hand-split-fix.mid
```

- [ ] **Step 6: If either listening check fails**

If the rock instrumental's split still sounds wrong in a way Step 3's metrics didn't already catch, or the piano output regressed: report the specific finding rather than tuning constants speculatively. This is real-audio ground truth overriding the plan's own pre-verified expectation — treat a surprise here as more informative than anything in this plan, and re-open Task 2 with the actual observed behavior in hand.

- [ ] **Step 7: Commit the harness change**

```bash
cd /Users/knguyen/VSC/Synthony
git add backend/scripts/quality_harness/run_baseline.py
git commit -m "$(cat <<'EOF'
test: add rock-instrumental track to the quality harness's fixed corpus

Keeps the real-audio track that surfaced assign_hands's multi-instrument
hand-split bug in the regression corpus going forward, alongside the
existing pop/rock and solo-piano sources.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Deferred (not in scope here)

- `assign_hands`'s duration-overlap gap (onsets close in time but not exactly simultaneous still piling into one hand via sustained durations) — flagged in the original `25d513b` commit that introduced the DP, independent of the bug this plan fixes.
- Any further tuning of `LONE_NOTE_RH_BIAS`, `ONSET_MERGE_WINDOW_SECONDS` (if added), or other constants beyond what Task 4's real-audio verification requires to pass — per this project's stated practice, tuning happens in response to an actual real-audio finding, not preemptively.
- Approach B (call-site-gated dual mode via an `allow_lone_note_dp` parameter) — the spec's documented fallback, not needed given Task 2's gate gets a clean regression suite pass; revisit only if Task 4 surfaces a problem Task 2's design can't absorb.
