# MAESTRO Ground-Truth Transcription Eval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone eval that measures Spec 1's solo-piano transcription accuracy against real MAESTRO ground-truth MIDI (note-level precision/recall/F1), closing the gap the existing quality harness has (it only diffs metrics run-over-run, never checks correctness against a known-right answer).

**Architecture:** A new sibling directory to `backend/scripts/quality_harness/`, `backend/scripts/ground_truth_eval/`. `clips.py` names 5 MAESTRO test-split clips; `fetch_maestro_clips.py` pulls just those clips out of MAESTRO's public ~108GB archive via HTTP range requests (no full-dataset download); `metrics.py` wraps `mir_eval.transcription` to score one clip; `eval.py` calls `transcribe_piano_audio_to_notes()` directly (no HTTP, no difficulty tiers) on each clip and reports per-clip + aggregate precision/recall/F1.

**Tech Stack:** Python 3.11, `mir_eval` (new dependency), `remotezip` (new dependency), `pretty_midi` (already present), the existing `backend/.venv`.

**Spec:** `docs/superpowers/specs/2026-09-16-maestro-ground-truth-eval-design.md`

## Global Constraints

- Report-only: no pass/fail threshold, no CI wiring, no non-zero exit on low scores.
- Raw transcription accuracy only: score `transcribe_piano_audio_to_notes()`'s output directly, never the full `/transcribe` HTTP pipeline or any difficulty tier.
- Onset+pitch matching only (`mir_eval.transcription.precision_recall_f1_overlap` with `offset_ratio=None`): onset tolerance 50ms, pitch tolerance 50 cents, offsets/durations ignored.
- 5 clips from MAESTRO's official **test** split (not train).
- `assets/` and `output/` under `ground_truth_eval/` are gitignored (binary audio/MIDI fixtures, same as `quality_harness/`).
- **Known environment quirk**: `backend/.venv`'s console-script wrappers (`.venv/bin/pytest`, `.venv/bin/pip`, etc.) have a stale shebang pointing at a `.venv-py311` directory that no longer exists on this machine. `.venv/bin/python` itself works fine. **Always invoke tools as `./.venv/bin/python -m pytest ...` / `./.venv/bin/python -m pip install ...`, never the bare `.venv/bin/pytest` / `.venv/bin/pip` wrapper** — confirmed working via `-m` invocation during planning.
- All commands below assume `cwd` = `/Users/knguyen/VSC/Synthony/backend`.

---

### Task 1: `metrics.py` — mir_eval scoring wrapper (TDD)

**Files:**
- Create: `backend/scripts/ground_truth_eval/clips.py`
- Create: `backend/scripts/ground_truth_eval/metrics.py`
- Create: `backend/scripts/ground_truth_eval/test_metrics.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces: `metrics.score_transcription(predicted: Iterable[object with .start/.end/.pitch], ground_truth_midi_path: Path) -> dict` with keys `precision: float, recall: float, f1: float, n_predicted: int, n_ground_truth: int`. `predicted` is duck-typed (works with `app.notation.types.NoteEvent`, `pretty_midi.Note`, or a plain namedtuple) — this module has no dependency on the `app` package.
- Produces: `clips.CLIPS`, a `list[dict]` with keys `name: str, audio_filename: str, midi_filename: str` (5 entries, MAESTRO test-split paths relative to the zip's `maestro-v3.0.0/` root, e.g. `"2009/MIDI-Unprocessed_11_R1_2009_06-09_ORIG_MID--AUDIO_11_R1_2009_11_R1_2009_07_WAV.wav"`).

- [ ] **Step 1: Add `mir_eval` to requirements and install it**

Edit `backend/requirements.txt`, add this line after `pretty_midi`:

```
mir_eval  # note-transcription precision/recall/F1 (onset+pitch matching) for the MAESTRO ground-truth eval
```

Run: `./.venv/bin/python -m pip install mir_eval`
Expected: installs successfully (pulls in `numpy`, `scipy`, `mido` if not already present — all already present in this venv).

- [ ] **Step 2: Write `clips.py`**

```python
"""5 clips from MAESTRO v3.0.0's official **test** split (not train --
this must stay a legitimate held-out eval), spanning 5 composers and
~65-170s durations. Paths are relative to the root folder inside both
MAESTRO zips (`maestro-v3.0.0/`), taken verbatim from
maestro-v3.0.0.csv's audio_filename/midi_filename columns."""
from __future__ import annotations

CLIPS: list[dict] = [
    {
        "name": "scriabin_entragete",
        "audio_filename": "2009/MIDI-Unprocessed_11_R1_2009_06-09_ORIG_MID--AUDIO_11_R1_2009_11_R1_2009_07_WAV.wav",
        "midi_filename": "2009/MIDI-Unprocessed_11_R1_2009_06-09_ORIG_MID--AUDIO_11_R1_2009_11_R1_2009_07_WAV.midi",
    },
    {
        "name": "debussy_etude7",
        "audio_filename": "2004/MIDI-Unprocessed_SMF_17_R1_2004_03-06_ORIG_MID--AUDIO_20_R2_2004_12_Track12_wav--1.wav",
        "midi_filename": "2004/MIDI-Unprocessed_SMF_17_R1_2004_03-06_ORIG_MID--AUDIO_20_R2_2004_12_Track12_wav--1.midi",
    },
    {
        "name": "scarlatti_k525",
        "audio_filename": "2008/MIDI-Unprocessed_09_R3_2008_01-07_ORIG_MID--AUDIO_09_R3_2008_wav--2.wav",
        "midi_filename": "2008/MIDI-Unprocessed_09_R3_2008_01-07_ORIG_MID--AUDIO_09_R3_2008_wav--2.midi",
    },
    {
        "name": "liszt_gnomenreigen",
        "audio_filename": "2008/MIDI-Unprocessed_14_R1_2008_01-05_ORIG_MID--AUDIO_14_R1_2008_wav--3.wav",
        "midi_filename": "2008/MIDI-Unprocessed_14_R1_2008_01-05_ORIG_MID--AUDIO_14_R1_2008_wav--3.midi",
    },
    {
        "name": "schubert_impromptu90no4",
        "audio_filename": "2015/MIDI-Unprocessed_R2_D1-2-3-6-7-8-11_mid--AUDIO-from_mp3_03_R2_2015_wav--1.wav",
        "midi_filename": "2015/MIDI-Unprocessed_R2_D1-2-3-6-7-8-11_mid--AUDIO-from_mp3_03_R2_2015_wav--1.midi",
    },
]
```

- [ ] **Step 3: Write the failing tests for `metrics.py`**

Create `backend/scripts/ground_truth_eval/test_metrics.py`:

```python
from collections import namedtuple
from pathlib import Path

import pretty_midi
import pytest

from metrics import score_transcription

Note = namedtuple("Note", ["start", "end", "pitch"])


def _write_ground_truth_midi(tmp_path: Path, notes) -> Path:
    midi = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    for n in notes:
        inst.notes.append(pretty_midi.Note(velocity=100, pitch=n.pitch, start=n.start, end=n.end))
    midi.instruments.append(inst)
    path = tmp_path / "ground_truth.mid"
    midi.write(str(path))
    return path


def test_perfect_match_scores_1_0(tmp_path):
    notes = [Note(0.0, 0.5, 60), Note(0.5, 1.0, 64)]
    gt_path = _write_ground_truth_midi(tmp_path, notes)
    result = score_transcription(notes, gt_path)
    assert result == {
        "precision": 1.0, "recall": 1.0, "f1": 1.0,
        "n_predicted": 2, "n_ground_truth": 2,
    }


def test_dropped_note_lowers_recall_not_precision(tmp_path):
    gt_path = _write_ground_truth_midi(tmp_path, [Note(0.0, 0.5, 60), Note(0.5, 1.0, 64)])
    predicted = [Note(0.0, 0.5, 60)]
    result = score_transcription(predicted, gt_path)
    assert result["precision"] == 1.0
    assert result["recall"] == 0.5
    assert result["f1"] == pytest.approx(2 / 3)


def test_extra_note_lowers_precision_not_recall(tmp_path):
    gt_path = _write_ground_truth_midi(tmp_path, [Note(0.0, 0.5, 60)])
    predicted = [Note(0.0, 0.5, 60), Note(0.5, 1.0, 67)]
    result = score_transcription(predicted, gt_path)
    assert result["precision"] == 0.5
    assert result["recall"] == 1.0
    assert result["f1"] == pytest.approx(2 / 3)


def test_pitch_outside_tolerance_does_not_match(tmp_path):
    gt_path = _write_ground_truth_midi(tmp_path, [Note(0.0, 0.5, 60)])
    predicted = [Note(0.0, 0.5, 61)]  # 1 semitone = 100 cents, outside the 50-cent tolerance
    result = score_transcription(predicted, gt_path)
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0


def test_onset_within_50ms_tolerance_matches(tmp_path):
    gt_path = _write_ground_truth_midi(tmp_path, [Note(0.0, 0.5, 60)])
    predicted = [Note(0.04, 0.5, 60)]
    result = score_transcription(predicted, gt_path)
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0


def test_onset_outside_50ms_tolerance_does_not_match(tmp_path):
    gt_path = _write_ground_truth_midi(tmp_path, [Note(0.0, 0.5, 60)])
    predicted = [Note(0.06, 0.5, 60)]
    result = score_transcription(predicted, gt_path)
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0


def test_empty_predicted_scores_zero_not_a_crash(tmp_path):
    gt_path = _write_ground_truth_midi(tmp_path, [Note(0.0, 0.5, 60)])
    result = score_transcription([], gt_path)
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["n_predicted"] == 0
    assert result["n_ground_truth"] == 1
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest backend/scripts/ground_truth_eval/test_metrics.py -v` (from `/Users/knguyen/VSC/Synthony`, or drop the `backend/` prefix if already `cwd`-ed into `backend/`)
Expected: FAIL / collection error — `metrics.py` doesn't exist yet (`ModuleNotFoundError: No module named 'metrics'`).

- [ ] **Step 5: Write `metrics.py`**

```python
"""Scores predicted piano-transcription notes against MAESTRO ground-truth
MIDI using mir_eval's standard note-transcription metric: onset within
+-50ms and pitch within +-50 cents, offsets ignored (duration accuracy
isn't part of this eval).

Predicted notes are duck-typed (any object with .start/.end/.pitch in
seconds/seconds/MIDI-note-number) so this module has no dependency on the
app package and can be tested standalone with plain namedtuples."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import mir_eval
import numpy as np
import pretty_midi


def _to_arrays(notes):
    notes = list(notes)
    if not notes:
        return np.zeros((0, 2)), np.zeros(0)
    intervals = np.array([[n.start, n.end] for n in notes], dtype=float)
    pitches = mir_eval.util.midi_to_hz(np.array([n.pitch for n in notes], dtype=float))
    return intervals, pitches


def _ground_truth_notes(midi_path: Path):
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    return [note for instrument in midi.instruments for note in instrument.notes]


def score_transcription(predicted: Iterable[object], ground_truth_midi_path: Path) -> dict:
    """Precision/recall/F1 of `predicted` notes against the ground-truth
    MIDI at `ground_truth_midi_path` (onset +-50ms, pitch +-50 cents,
    offsets ignored)."""
    est_intervals, est_pitches = _to_arrays(predicted)
    ref_notes = _ground_truth_notes(ground_truth_midi_path)
    ref_intervals, ref_pitches = _to_arrays(ref_notes)

    precision, recall, f1, _avg_overlap_ratio = mir_eval.transcription.precision_recall_f1_overlap(
        ref_intervals, ref_pitches, est_intervals, est_pitches, offset_ratio=None,
    )
    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "n_predicted": len(est_pitches),
        "n_ground_truth": len(ref_pitches),
    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest backend/scripts/ground_truth_eval/test_metrics.py -v`
Expected: 7 passed.

- [ ] **Step 7: Run the full backend suite to confirm no collisions/regressions**

Run: `./.venv/bin/python -m pytest -q` (from `backend/`)
Expected: 278 + 7 = 285 passed (the new file is auto-discovered; confirm no `test_metrics`/`metrics` module-name collision with `quality_harness/metrics.py`, which has no test file so none is expected).

- [ ] **Step 8: Commit**

```bash
git add backend/requirements.txt backend/scripts/ground_truth_eval/clips.py backend/scripts/ground_truth_eval/metrics.py backend/scripts/ground_truth_eval/test_metrics.py
git commit -m "feat: add mir_eval-based note-transcription scoring for the MAESTRO ground-truth eval"
```

---

### Task 2: `fetch_maestro_clips.py` — pull the 5 clips without downloading the full dataset

**Files:**
- Create: `backend/scripts/ground_truth_eval/fetch_maestro_clips.py`
- Modify: `backend/requirements.txt`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `clips.CLIPS` (from Task 1).
- Produces: populates `backend/scripts/ground_truth_eval/assets/<name>.wav` and `assets/<name>.midi` for every entry in `CLIPS`. No importable interface — this is a one-time setup script, run directly.

This task has no automated test (network-dependent orchestration script, same as `quality_harness/run_baseline.py` — not part of `backend/tests/`). It's verified by actually running it in Step 4 below and confirming the real files land in `assets/`.

**Why this needs `remotezip`, not a plain download**: MAESTRO's audio is only distributed inside one ~108GB zip (`maestro-v3.0.0.zip`); Google Cloud Storage does not serve its individual extracted members as separate URLs (confirmed: direct per-file URLs 404). `remotezip` reads the zip's central directory and fetches only the requested member's bytes via HTTP range requests — confirmed during planning: extracting one ~85MB member took ~5 seconds, not the time to download the full archive. The MIDI-only zip (`maestro-v3.0.0-midi.zip`, ~58MB total) is small enough it wouldn't matter either way, but using `remotezip` for both keeps one code path.

- [ ] **Step 1: Add `remotezip` to requirements and install it**

Edit `backend/requirements.txt`, add this line after the new `mir_eval` line:

```
remotezip  # fetches individual members from MAESTRO's ~108GB zip via HTTP range requests, no full download
```

Run: `./.venv/bin/python -m pip install remotezip`
Expected: installs successfully.

- [ ] **Step 2: Write `fetch_maestro_clips.py`**

```python
#!/usr/bin/env python3
"""One-time setup script: downloads the 5 (audio, MIDI) pairs named in
clips.CLIPS from MAESTRO v3.0.0's official public hosting into assets/.

Uses remotezip to fetch only the needed members from Google's public
GCS-hosted zips (~108GB audio zip, ~58MB MIDI-only zip) via HTTP range
requests -- never downloads either zip in full. Safe to re-run: skips any
clip file that already exists in assets/.

USAGE
  cd backend/scripts/ground_truth_eval
  ../../.venv/bin/python fetch_maestro_clips.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from remotezip import RemoteZip

sys.path.insert(0, str(Path(__file__).parent))
from clips import CLIPS  # noqa: E402

ASSETS_DIR = Path(__file__).parent / "assets"

_AUDIO_ZIP_URL = "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0.zip"
_MIDI_ZIP_URL = "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0-midi.zip"
_ZIP_ROOT = "maestro-v3.0.0/"


def _fetch_one(zip_url: str, member_path: str, dest: Path) -> None:
    if dest.exists():
        print(f"  already have {dest.name}, skipping")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with RemoteZip(zip_url) as zf, zf.open(_ZIP_ROOT + member_path) as src:
        dest.write_bytes(src.read())
    print(f"  fetched {dest.name} ({dest.stat().st_size} bytes)")


def main() -> int:
    for clip in CLIPS:
        print(f"[{clip['name']}]")
        _fetch_one(_AUDIO_ZIP_URL, clip["audio_filename"], ASSETS_DIR / f"{clip['name']}.wav")
        _fetch_one(_MIDI_ZIP_URL, clip["midi_filename"], ASSETS_DIR / f"{clip['name']}.midi")
    print(f"\nDone. Clips in {ASSETS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Add the gitignore entries**

Edit `.gitignore`, add after the existing `backend/scripts/quality_harness/output/` line (around line 27):

```
backend/scripts/ground_truth_eval/assets/
backend/scripts/ground_truth_eval/output/
```

- [ ] **Step 4: Run it for real and verify the assets land**

Run: `cd backend/scripts/ground_truth_eval && ../../.venv/bin/python fetch_maestro_clips.py`
Expected: prints `fetched ...` for all 10 files (5 `.wav` + 5 `.midi`), completes in well under a minute (each member fetch took ~5s or less during planning verification). Then run: `ls -la backend/scripts/ground_truth_eval/assets/` and confirm 10 files totaling roughly 100-150MB (audio dominates; MIDI files are a few KB-tens of KB each).

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/scripts/ground_truth_eval/fetch_maestro_clips.py .gitignore
git commit -m "feat: add the MAESTRO clip fetcher (range-request partial download, no full dataset pull)"
```

(`assets/` itself is gitignored and stays uncommitted, same as `quality_harness/assets/`.)

---

### Task 3: `eval.py` — run the eval end-to-end and report real numbers

**Files:**
- Create: `backend/scripts/ground_truth_eval/eval.py`
- Modify: `RESUME.md`
- Modify: `TAKEAWAYS.md`

**Interfaces:**
- Consumes: `clips.CLIPS` (Task 1), `metrics.score_transcription` (Task 1), `app.transcription.audio_to_midi.transcribe_piano_audio_to_notes` (existing, `backend/app/transcription/audio_to_midi.py:27`) which returns a `PianoTranscriptionResult` with a `.notes` attribute (`list[NoteEvent]`).
- Produces: `backend/scripts/ground_truth_eval/output/<label>/results.json`.

No automated test for this file either (CLI orchestration script that drives real model inference on real audio — same category as `quality_harness/run_baseline.py`). It's verified by actually running it against the real fetched clips in Step 3 and reading real output.

- [ ] **Step 1: Write `eval.py`**

```python
#!/usr/bin/env python3
"""Ground-truth transcription accuracy eval: runs Spec 1's solo-piano
transcription (transcribe_piano_audio_to_notes -- no HTTP, no difficulty
tiers) directly against the 5 MAESTRO clips in assets/, scores each
against its paired ground-truth MIDI via metrics.score_transcription, and
reports precision/recall/F1 per clip plus a micro-averaged aggregate.

Report-only: no pass/fail threshold, no CI wiring. Numbers are for a human
to read and judge, same spirit as backend/scripts/quality_harness/.

USAGE
  cd backend/scripts/ground_truth_eval
  ../../.venv/bin/python fetch_maestro_clips.py   # one-time, populates assets/
  ../../.venv/bin/python eval.py --label baseline
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from app.transcription.audio_to_midi import transcribe_piano_audio_to_notes  # noqa: E402
from clips import CLIPS  # noqa: E402
from metrics import score_transcription  # noqa: E402

ASSETS_DIR = SCRIPT_DIR / "assets"
OUTPUT_DIR = SCRIPT_DIR / "output"


def run_one(clip: dict) -> dict:
    name = clip["name"]
    audio_path = ASSETS_DIR / f"{name}.wav"
    midi_path = ASSETS_DIR / f"{name}.midi"
    print(f"[{name}] transcribing ...", flush=True)
    result = transcribe_piano_audio_to_notes(str(audio_path))
    scores = score_transcription(result.notes, midi_path)
    scores["name"] = name
    print(
        f"[{name}] precision={scores['precision']:.3f} recall={scores['recall']:.3f} "
        f"f1={scores['f1']:.3f} ({scores['n_predicted']} predicted / "
        f"{scores['n_ground_truth']} ground truth)"
    )
    return scores


def _aggregate(per_clip: list) -> dict:
    """Micro-average across all notes: reconstructs each clip's true-positive
    count from its own precision (precision == n_correct / n_predicted)
    rather than averaging per-clip F1 scores directly, so a clip with more
    notes weighs proportionally more in the aggregate."""
    total_predicted = sum(c["n_predicted"] for c in per_clip)
    total_ground_truth = sum(c["n_ground_truth"] for c in per_clip)
    total_correct = sum(c["precision"] * c["n_predicted"] for c in per_clip)
    precision = total_correct / total_predicted if total_predicted else 0.0
    recall = total_correct / total_ground_truth if total_ground_truth else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "n_predicted": total_predicted,
        "n_ground_truth": total_ground_truth,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", required=True, help="Run label, used as the output subdirectory name.")
    args = parser.parse_args()

    missing = [
        c["name"] for c in CLIPS
        if not (ASSETS_DIR / f"{c['name']}.wav").exists() or not (ASSETS_DIR / f"{c['name']}.midi").exists()
    ]
    if missing:
        print(f"ERROR: missing assets for {missing}. Run fetch_maestro_clips.py first.")
        return 1

    per_clip = [run_one(clip) for clip in CLIPS]
    aggregate = _aggregate(per_clip)

    print(
        f"\nAggregate (micro-averaged over {aggregate['n_ground_truth']} ground-truth notes): "
        f"precision={aggregate['precision']:.3f} recall={aggregate['recall']:.3f} f1={aggregate['f1']:.3f}"
    )

    summary = {"label": args.label, "per_clip": per_clip, "aggregate": aggregate}
    out_path = OUTPUT_DIR / args.label / "results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Sanity-check imports before the full run**

Run: `cd backend/scripts/ground_truth_eval && ../../.venv/bin/python -c "import eval"`
Expected: no errors (confirms `app.transcription.audio_to_midi` imports cleanly from this script's location — the piano model checkpoint itself is only downloaded lazily on first real transcription call, not at import time).

- [ ] **Step 3: Run the eval end-to-end against the real fetched clips**

Run: `cd backend/scripts/ground_truth_eval && ../../.venv/bin/python eval.py --label baseline`
Expected: for each of the 5 clips, a `[name] transcribing ...` line followed by a `precision=... recall=... f1=...` line (the first clip run will also trigger the one-time ~180MB piano-model checkpoint download if not already cached at `~/piano_transcription_inference_data/`, per `_ensure_piano_checkpoint()` in `app/transcription/audio_to_midi.py`). Ends with an aggregate line and `Wrote backend/scripts/ground_truth_eval/output/baseline/results.json`. Read that file's contents (`cat` or your file-read tool) and confirm it has real, non-placeholder precision/recall/F1 numbers — this is the actual deliverable of the whole plan, so don't skip reading it.

- [ ] **Step 4: Record the real numbers in `RESUME.md` and `TAKEAWAYS.md`**

Update `RESUME.md`'s "Queued: 2026-09-16 portfolio-review Improvement Backlog" section: mark item 2a done, replacing its bullet with a short summary of what was built (`backend/scripts/ground_truth_eval/`) and the actual aggregate precision/recall/F1 numbers from Step 3's `results.json` (copy the real numbers, not a placeholder). Note that 2b (difficulty-tier validation) is now unblocked.

Add a `TAKEAWAYS.md` entry noting the aggregate numbers and, if they're notably low or high, one sentence on what that suggests about `piano_transcription_inference`'s real-world accuracy versus its own reported training-set F1 (`note_F1=0.9677` is baked into the checkpoint filename at `backend/app/transcription/audio_to_midi.py:20` — a natural point of comparison).

- [ ] **Step 5: Run the full backend suite one more time**

Run: `./.venv/bin/python -m pytest -q` (from `backend/`)
Expected: 285 passed (unchanged from Task 1's Step 7 — `eval.py` and `fetch_maestro_clips.py` add no new pytest tests).

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/ground_truth_eval/eval.py RESUME.md TAKEAWAYS.md
git commit -m "feat: add the MAESTRO ground-truth eval CLI, record real precision/recall/F1 numbers"
```
