from music21 import stream, note, clef

from app.difficulty.range_shift import shift_into_range


def test_note_above_range_is_shifted_down_an_octave():
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("C6"))  # MIDI 84

    shifted = shift_into_range(part, low=60, high=72)  # C4-C5

    pitches = [n.pitch.midi for n in shifted.flatten().notes]
    assert pitches == [72]  # C5, same pitch class, within range


def test_note_below_range_is_shifted_up_an_octave():
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("C2"))  # MIDI 36

    shifted = shift_into_range(part, low=60, high=72)

    pitches = [n.pitch.midi for n in shifted.flatten().notes]
    assert pitches == [60]


def test_note_already_in_range_is_unchanged():
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("E4"))  # MIDI 64

    shifted = shift_into_range(part, low=60, high=72)

    pitches = [n.pitch.midi for n in shifted.flatten().notes]
    assert pitches == [64]


def test_preserves_clef_from_input_part():
    part = stream.Part(id="RH")
    part.insert(0, clef.TrebleClef())
    part.insert(0.0, note.Note("E4"))  # MIDI 64

    shifted = shift_into_range(part, low=60, high=72)

    clefs = shifted.getElementsByClass(clef.Clef)
    assert len(clefs) == 1
    assert isinstance(clefs[0], clef.TrebleClef)


def test_note_at_low_boundary_stays_unchanged():
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("C4"))  # MIDI 60 (exactly at low boundary)

    shifted = shift_into_range(part, low=60, high=72)

    pitches = [n.pitch.midi for n in shifted.flatten().notes]
    assert pitches == [60]


def test_note_at_high_boundary_stays_unchanged():
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("C5"))  # MIDI 72 (exactly at high boundary)

    shifted = shift_into_range(part, low=60, high=72)

    pitches = [n.pitch.midi for n in shifted.flatten().notes]
    assert pitches == [72]
