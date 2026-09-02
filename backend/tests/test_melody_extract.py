from app.melody.extract import reduce_to_monophonic
from app.notation.types import NoteEvent


def test_reduce_to_monophonic_passes_through_non_overlapping_notes():
    notes = [
        NoteEvent(start=0.0, end=0.5, pitch=60),
        NoteEvent(start=0.5, end=1.0, pitch=62),
    ]
    assert reduce_to_monophonic(notes) == notes


def test_reduce_to_monophonic_keeps_higher_pitch_when_notes_overlap():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=60),  # discarded — overlaps, lower
        NoteEvent(start=0.2, end=0.8, pitch=67),   # kept — higher pitch
    ]
    assert reduce_to_monophonic(notes) == [notes[1]]


def test_reduce_to_monophonic_discards_lower_pitch_overlapping_note():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=67),  # kept — higher pitch, processed first
        NoteEvent(start=0.2, end=0.5, pitch=60),   # discarded — overlaps, lower
    ]
    assert reduce_to_monophonic(notes) == [notes[0]]
