import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.notation.types import NoteEvent
from app.notation.hand_split import notes_to_grand_staff, get_hand_parts, NOTATION_GRID
from app.export import export_musicxml


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


def test_messy_audio_timing_produces_expressible_durations():
    """Regression: real audio timing produces non-power-of-two fractions.
    Verify that _to_music21_note rounds durations to NOTATION_GRID."""
    # Start/end chosen so duration doesn't land on clean grid:
    # duration = (0.873 - 0.251) / 0.5 = 0.622 / 0.5 = 1.244 quarterLength
    # After rounding to 0.125 grid: 1.25 (1.244 rounded nearest 32nd note)
    notes = [NoteEvent(start=0.251, end=0.873, pitch=60)]
    score = notes_to_grand_staff(notes)
    rh, lh = get_hand_parts(score)

    rh_notes = list(rh.flatten().notes)
    assert len(rh_notes) == 1

    # Verify duration is a multiple of NOTATION_GRID (expressible in MusicXML)
    duration = rh_notes[0].duration.quarterLength
    rounded_duration = round(duration / NOTATION_GRID) * NOTATION_GRID
    assert abs(duration - rounded_duration) < 1e-10, \
        f"Duration {duration} is not on NOTATION_GRID {NOTATION_GRID}"


def test_messy_offset_is_quantized_to_grid():
    """Verify that note onsets (offsets) are also rounded to NOTATION_GRID."""
    # Start time that produces non-clean offset:
    # offset = 0.333 / 0.5 = 0.666 quarterLength
    # After rounding to 0.125 grid: 0.625 or 0.75
    notes = [NoteEvent(start=0.333, end=0.5, pitch=60)]
    score = notes_to_grand_staff(notes)
    rh, lh = get_hand_parts(score)

    rh_notes = list(rh.flatten().notes)
    assert len(rh_notes) == 1

    # Get the offset from the note's position in the part
    # music21 stores offset/quarterStart
    offset = rh_notes[0].offset
    rounded_offset = round(offset / NOTATION_GRID) * NOTATION_GRID
    assert abs(offset - rounded_offset) < 1e-10, \
        f"Offset {offset} is not on NOTATION_GRID {NOTATION_GRID}"


def test_score_with_messy_timing_exports_to_musicxml():
    """Integration test: a score built from messy audio timing can be
    exported to MusicXML without MusicXMLExportException."""
    # Multiple notes with fractional timing that would fail without quantization
    notes = [
        NoteEvent(start=0.124, end=0.651, pitch=60),  # Non-clean duration
        NoteEvent(start=0.124, end=0.623, pitch=48),  # Different non-clean duration
    ]
    score = notes_to_grand_staff(notes)

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_export.musicxml"
        # This should not raise MusicXMLExportException
        result = export_musicxml(score, output_path)
        assert result.exists(), "MusicXML export failed or file not created"
