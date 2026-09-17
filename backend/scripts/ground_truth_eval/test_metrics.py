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
