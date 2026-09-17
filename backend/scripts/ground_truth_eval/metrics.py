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
