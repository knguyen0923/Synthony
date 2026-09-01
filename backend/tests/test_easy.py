from pathlib import Path
from tempfile import TemporaryDirectory

from music21 import stream, note, clef

from app.notation.hand_split import get_hand_parts
from app.difficulty.easy import to_easy
from app.export import export_musicxml


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
    assert notes[0].pitch.midi == 72  # C6 (MIDI 84) octave-shifted down to C5 (MIDI 72)


def test_easy_output_has_braced_part_group_in_exported_musicxml():
    score = _score(rh_notes=[(0.0, "C5")], lh_notes=[(0.0, "C3")])
    easy_score = to_easy(score)

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_easy_brace.musicxml"
        export_musicxml(easy_score, output_path)
        xml = output_path.read_text()

    assert "<part-group" in xml
    assert "<group-symbol>brace</group-symbol>" in xml


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


def test_easy_preserves_lh_clef():
    """Verify that LH output retains its BassClef from the input."""
    rh = stream.Part(id="RH")
    rh.insert(0, note.Note("C6"))
    lh = stream.Part(id="LH")
    lh.insert(0, clef.BassClef())
    lh.insert(0, note.Note("C3"))
    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)

    easy_score = to_easy(score)
    _, easy_lh = get_hand_parts(easy_score)
    clefs = easy_lh.getElementsByClass(clef.BassClef)
    assert len(clefs) == 1
