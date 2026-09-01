from pathlib import Path
from tempfile import TemporaryDirectory

from music21 import stream, note

from app.notation.hand_split import get_hand_parts, notes_to_grand_staff
from app.notation.types import NoteEvent
from app.difficulty.hard import to_hard
from app.export import export_musicxml


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


def test_hard_output_has_braced_part_group_in_exported_musicxml():
    """Hard's deepcopy passthrough must preserve the grand-staff brace that
    notes_to_grand_staff attaches to its input score."""
    notes = [
        NoteEvent(start=0.0, end=0.5, pitch=60),
        NoteEvent(start=0.0, end=0.5, pitch=48),
    ]
    score = notes_to_grand_staff(notes)
    hard_score = to_hard(score)

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_hard_brace.musicxml"
        export_musicxml(hard_score, output_path)
        xml = output_path.read_text()

    assert "<part-group" in xml
    assert "<group-symbol>brace</group-symbol>" in xml


def test_hard_output_has_part_names_and_title_in_exported_musicxml():
    """Hard's deepcopy passthrough must preserve the part names and title
    that notes_to_grand_staff attaches to its input score."""
    notes = [
        NoteEvent(start=0.0, end=0.5, pitch=60),
        NoteEvent(start=0.0, end=0.5, pitch=48),
    ]
    score = notes_to_grand_staff(notes, title="Clair de Lune")
    hard_score = to_hard(score)

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_hard_names.musicxml"
        export_musicxml(hard_score, output_path)
        xml = output_path.read_text()

    assert "<part-name>Right Hand</part-name>" in xml
    assert "<part-name>Left Hand</part-name>" in xml
    assert "<work-title>Clair de Lune</work-title>" in xml
