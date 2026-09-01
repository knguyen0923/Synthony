from app.notation.types import NoteEvent
from app.notation.hand_split import notes_to_grand_staff, get_hand_parts


def test_lone_low_note_is_melody_and_goes_to_right_hand():
    notes = [NoteEvent(start=0.0, end=0.5, pitch=48)]  # C3, alone = melody
    score = notes_to_grand_staff(notes)
    rh, lh = get_hand_parts(score)
    assert [n.pitch.midi for n in rh.flatten().notes] == [48]
    assert list(lh.flatten().notes) == []


def test_highest_simultaneous_note_is_melody_rest_are_accompaniment():
    notes = [
        NoteEvent(start=0.0, end=0.5, pitch=60),  # C4 - melody (highest)
        NoteEvent(start=0.0, end=0.5, pitch=48),  # C3 - accompaniment
        NoteEvent(start=0.0, end=0.5, pitch=52),  # E3 - accompaniment
    ]
    score = notes_to_grand_staff(notes)
    rh, lh = get_hand_parts(score)
    assert sorted(n.pitch.midi for n in rh.flatten().notes) == [60]
    assert sorted(n.pitch.midi for n in lh.flatten().notes) == [48, 52]


def test_parts_have_correct_clefs():
    notes = [NoteEvent(start=0.0, end=0.5, pitch=60)]
    score = notes_to_grand_staff(notes)
    rh, lh = get_hand_parts(score)
    assert rh.getElementsByClass("Clef").first().sign == "G"
    assert lh.getElementsByClass("Clef").first().sign == "F"
