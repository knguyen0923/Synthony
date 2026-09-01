from pathlib import Path
from tempfile import TemporaryDirectory

from music21 import stream, note, clef

from app.notation.hand_split import get_hand_parts
from app.difficulty.medium import to_medium
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


def test_medium_output_has_braced_part_group_in_exported_musicxml():
    score = _score(rh_notes=[(0.0, "C4")], lh_notes=[(0.0, "C3")])
    medium_score = to_medium(score)

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_medium_brace.musicxml"
        export_musicxml(medium_score, output_path)
        xml = output_path.read_text()

    assert "<part-group" in xml
    assert "<group-symbol>brace</group-symbol>" in xml


def test_medium_melody_quantizes_to_eighth_grid():
    score = _score(
        rh_notes=[(0.0, "C4"), (0.4, "D4"), (0.5, "E4")],
        lh_notes=[],
    )
    medium_score = to_medium(score)
    rh, _ = get_hand_parts(medium_score)
    offsets = sorted(n.offset for n in rh.flatten().notes)
    # grid = 0.5: slot 0 keeps first note (C4 at 0.0), slot 0.5 keeps E4
    assert offsets == [0.0, 0.5]


def test_medium_bass_voices_up_to_three_distinct_pitch_classes():
    score = _score(
        rh_notes=[],
        lh_notes=[(0.0, "C3"), (0.0, "C4"), (0.0, "E3"), (0.0, "G3"), (0.0, "B3")],
    )
    medium_score = to_medium(score)
    _, lh = get_hand_parts(medium_score)
    notes = sorted(lh.flatten().notes, key=lambda n: n.pitch.midi)
    pitch_names = [n.pitch.name for n in notes]
    assert len(notes) == 3               # capped at 3 tones
    assert pitch_names == ["C", "E", "G"]  # doubled C4 dropped; B3 excluded (4th tone)
    assert notes[0].pitch.midi == 48      # lowest C instance kept (C3, not C4)


def test_medium_preserves_lh_clef():
    """Verify that LH output retains its BassClef from the input."""
    rh = stream.Part(id="RH")
    rh.insert(0, note.Note("C4"))
    lh = stream.Part(id="LH")
    lh.insert(0, clef.BassClef())
    lh.insert(0, note.Note("C3"))
    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)

    medium_score = to_medium(score)
    _, medium_lh = get_hand_parts(medium_score)
    clefs = medium_lh.getElementsByClass(clef.BassClef)
    assert len(clefs) == 1
