from app.lh.extract import HARD_LH_RANGE, build_lh_part, cap_simultaneous_notes, extract_lh_notes
from app.notation.types import NoteEvent


def test_cap_simultaneous_notes_passes_through_when_under_the_cap():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=48, velocity=0.6),
        NoteEvent(start=0.0, end=1.0, pitch=52, velocity=0.7),
    ]
    assert cap_simultaneous_notes(notes, max_voices=3) == notes


def test_cap_simultaneous_notes_drops_the_weakest_note_over_the_cap():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=48, velocity=0.9),
        NoteEvent(start=0.0, end=1.0, pitch=52, velocity=0.5),
        NoteEvent(start=0.0, end=1.0, pitch=55, velocity=0.7),
        NoteEvent(start=0.0, end=1.0, pitch=59, velocity=0.2),  # weakest — dropped
    ]
    result = cap_simultaneous_notes(notes, max_voices=3)
    assert len(result) == 3
    assert notes[3] not in result


def test_cap_simultaneous_notes_evicts_a_held_note_when_a_stronger_one_arrives_later():
    notes = [
        NoteEvent(start=0.0, end=2.0, pitch=48, velocity=0.3),  # weak, held from t=0
        NoteEvent(start=0.0, end=2.0, pitch=52, velocity=0.6),
        NoteEvent(start=1.0, end=2.0, pitch=55, velocity=0.9),  # arrives later, stronger than the weak held note
    ]
    result = cap_simultaneous_notes(notes, max_voices=2)
    assert notes[0] not in result  # evicted — still sounding at t=1.0 but weakest
    assert notes[1] in result
    assert notes[2] in result


def test_cap_simultaneous_notes_favors_the_earlier_note_on_a_confidence_tie():
    notes = [
        NoteEvent(start=0.0, end=1.0, pitch=48, velocity=0.5),
        NoteEvent(start=0.0, end=1.0, pitch=52, velocity=0.5),
        NoteEvent(start=0.2, end=0.8, pitch=55, velocity=0.5),  # same confidence, arrives later
    ]
    result = cap_simultaneous_notes(notes, max_voices=2)
    assert result == [notes[0], notes[1]]


def test_cap_simultaneous_notes_frees_a_voice_once_a_held_note_ends():
    notes = [
        NoteEvent(start=0.0, end=0.5, pitch=48, velocity=0.9),
        NoteEvent(start=0.0, end=0.5, pitch=52, velocity=0.8),
        NoteEvent(start=0.6, end=1.0, pitch=55, velocity=0.1),  # starts after both earlier notes ended
    ]
    result = cap_simultaneous_notes(notes, max_voices=2)
    assert result == notes  # no eviction needed — the first two had already ended


def test_extract_lh_notes_caps_to_max_voices(monkeypatch):
    import app.lh.extract as lh_extract_module

    fake_notes = [
        NoteEvent(start=0.0, end=1.0, pitch=48, velocity=0.9),
        NoteEvent(start=0.0, end=1.0, pitch=52, velocity=0.8),
        NoteEvent(start=0.0, end=1.0, pitch=55, velocity=0.1),
    ]
    monkeypatch.setattr(lh_extract_module, "transcribe_audio_to_notes", lambda audio_path: fake_notes)

    notes = extract_lh_notes("fake/path.wav", max_voices=2)
    assert len(notes) == 2


def test_extract_lh_notes_detects_content_near_a4(synthetic_piano_wav):
    notes = extract_lh_notes(str(synthetic_piano_wav))
    assert len(notes) >= 1
    pitches = [n.pitch for n in notes]
    assert any(abs(p - 69) <= 2 for p in pitches)  # A4 = MIDI 69, same synthetic tone as melody's fixture


def test_build_lh_part_shifts_notes_into_the_hard_range():
    notes = [NoteEvent(start=0.0, end=1.0, pitch=84)]  # C6, above HARD_LH_RANGE
    part = build_lh_part(notes)
    pitches = [n.pitch.midi for n in part.flatten().notes]
    assert all(HARD_LH_RANGE[0] <= p <= HARD_LH_RANGE[1] for p in pitches)
