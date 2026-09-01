from music21 import stream, note

from app.notation.hand_split import get_hand_parts
from app.difficulty.hard import to_hard


def test_hard_is_an_unmodified_deep_copy():
    rh = stream.Part(id="RH")
    rh.insert(0.0, note.Note("C7"))  # deliberately out of any "range" window
    lh = stream.Part(id="LH")
    lh.insert(0.0, note.Note("C2"))
    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)

    hard_score = to_hard(score)

    hard_rh, hard_lh = get_hand_parts(hard_score)
    assert [n.pitch.midi for n in hard_rh.flatten().notes] == [96]  # unchanged
    assert [n.pitch.midi for n in hard_lh.flatten().notes] == [36]  # unchanged
    assert hard_score is not score  # independent copy, not the same object
