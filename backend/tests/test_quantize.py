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
