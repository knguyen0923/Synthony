from app.melody.extract import reduce_to_monophonic
from app.notation.types import NoteEvent


def test_reduce_to_monophonic_passes_through_non_overlapping_notes():
    notes = [
        NoteEvent(start=0.0, end=0.5, pitch=60),
        NoteEvent(start=0.5, end=1.0, pitch=62),
    ]
    assert reduce_to_monophonic(notes) == notes


def test_reduce_to_monophonic_keeps_higher_confidence_when_notes_overlap():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=67, velocity=0.3),  # discarded — lower confidence despite higher pitch
        NoteEvent(start=0.2, end=0.8, pitch=60, velocity=0.9),   # kept — higher confidence despite lower pitch
    ]
    assert reduce_to_monophonic(notes) == [notes[1]]


def test_reduce_to_monophonic_discards_lower_confidence_overlapping_note():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=60, velocity=0.9),  # kept — higher confidence, processed first
        NoteEvent(start=0.2, end=0.5, pitch=67, velocity=0.3),   # discarded — overlaps, lower confidence despite higher pitch
    ]
    assert reduce_to_monophonic(notes) == [notes[0]]


def test_reduce_to_monophonic_favors_the_earlier_note_on_a_confidence_tie():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=60, velocity=0.8),
        NoteEvent(start=0.2, end=0.8, pitch=72, velocity=0.8),  # same confidence, higher pitch — no longer wins
    ]
    assert reduce_to_monophonic(notes) == [notes[0]]


from app.melody.extract import extract_melody_notes


def test_extract_melody_notes_detects_note_near_a4(synthetic_piano_wav):
    notes = extract_melody_notes(str(synthetic_piano_wav))

    assert len(notes) >= 1
    pitches = [n.pitch for n in notes]
    assert any(abs(p - 69) <= 2 for p in pitches)  # A4 = MIDI 69, +/-2 semitone tolerance
