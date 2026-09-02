from music21 import stream, note, clef

from app.difficulty.quantize import quantize_part


def test_keeps_first_note_per_slot_and_drops_the_rest():
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("C4"))
    part.insert(0.1, note.Note("D4"))  # same 1.0-quarterLength grid slot as C4
    part.insert(1.0, note.Note("E4"))

    quantized = quantize_part(part, grid=1.0)

    pitches = [n.pitch.name for n in quantized.flatten().notes]
    assert pitches == ["C", "E"]


def test_quantized_notes_are_snapped_to_the_grid():
    part = stream.Part(id="RH")
    part.insert(0.3, note.Note("C4"))

    quantized = quantize_part(part, grid=1.0)

    offsets = [n.offset for n in quantized.flatten().notes]
    assert offsets == [0.0]


def test_preserves_clef_from_input_part():
    part = stream.Part(id="RH")
    part.insert(0, clef.TrebleClef())
    part.insert(0.0, note.Note("C4"))

    quantized = quantize_part(part, grid=1.0)

    clefs = quantized.getElementsByClass(clef.Clef)
    assert len(clefs) == 1
    assert isinstance(clefs[0], clef.TrebleClef)


def test_note_already_on_grid_line_stays_unchanged():
    part = stream.Part(id="RH")
    part.insert(1.0, note.Note("C4"))

    quantized = quantize_part(part, grid=1.0)

    offsets = [n.offset for n in quantized.flatten().notes]
    assert offsets == [1.0]


def test_max_voices_default_still_keeps_first_note_per_slot():
    # Regression: explicit max_voices=1 must match the pre-existing default.
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("C4"))
    part.insert(0.1, note.Note("D4"))
    quantized = quantize_part(part, grid=1.0, max_voices=1)
    pitches = [n.pitch.name for n in quantized.flatten().notes]
    assert pitches == ["C"]


def test_max_voices_caps_notes_per_slot_by_velocity():
    part = stream.Part(id="LH")
    for pitch_name, velocity in [("C3", 0.9), ("E3", 0.5), ("G3", 0.7), ("B3", 0.3)]:
        n = note.Note(pitch_name)
        n.volume.velocityScalar = velocity
        part.insert(0.0, n)

    quantized = quantize_part(part, grid=1.0, max_voices=3)

    pitches = sorted(n.pitch.name for n in quantized.flatten().notes)
    assert pitches == ["C", "E", "G"]  # B3 (lowest velocity) dropped


def test_max_voices_dedups_repeated_pitch_class_keeping_higher_velocity():
    part = stream.Part(id="LH")
    n1 = note.Note("C3")
    n1.volume.velocityScalar = 0.4
    n2 = note.Note("C4")
    n2.volume.velocityScalar = 0.9
    part.insert(0.0, n1)
    part.insert(0.0, n2)

    quantized = quantize_part(part, grid=1.0, max_voices=3)

    notes = list(quantized.flatten().notes)
    assert len(notes) == 1
    assert notes[0].pitch.midi == 60  # C4 (higher-velocity instance) kept, not C3


def test_max_voices_preserves_clef():
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    n = note.Note("C3")
    n.volume.velocityScalar = 0.5
    part.insert(0.0, n)

    quantized = quantize_part(part, grid=1.0, max_voices=3)

    clefs = quantized.getElementsByClass(clef.Clef)
    assert len(clefs) == 1
    assert isinstance(clefs[0], clef.BassClef)
