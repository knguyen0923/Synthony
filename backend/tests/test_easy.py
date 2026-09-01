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
