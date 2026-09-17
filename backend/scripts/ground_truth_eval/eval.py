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
