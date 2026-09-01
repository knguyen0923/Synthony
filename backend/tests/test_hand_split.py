import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from music21 import clef

from app.notation.types import NoteEvent
from app.notation.hand_split import notes_to_grand_staff, get_hand_parts, NOTATION_GRID
from app.export import export_musicxml


def test_grand_staff_has_braced_part_group_in_exported_musicxml():
    """RH/LH must render as a connected piano grand staff (braced), not two
    independent unbraced staves, in the exported MusicXML."""
    notes = [
        NoteEvent(start=0.0, end=0.5, pitch=60),  # melody -> RH
        NoteEvent(start=0.0, end=0.5, pitch=48),  # accompaniment -> LH
    ]
    score = notes_to_grand_staff(notes)

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_brace.musicxml"
        export_musicxml(score, output_path)
        xml = output_path.read_text()

    assert "<part-group" in xml
    assert "<group-symbol>brace</group-symbol>" in xml


def test_grand_staff_parts_are_named_in_exported_musicxml():
    """Without an explicit part name, music21 exports an empty <part-name>,
    which viewers render as the internal id (an opaque hex string) instead
    of a human-readable instrument label."""
    notes = [
        NoteEvent(start=0.0, end=0.5, pitch=60),
        NoteEvent(start=0.0, end=0.5, pitch=48),
    ]
    score = notes_to_grand_staff(notes)

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_names.musicxml"
        export_musicxml(score, output_path)
        xml = output_path.read_text()

    assert "<part-name>Right Hand</part-name>" in xml
    assert "<part-name>Left Hand</part-name>" in xml


def test_grand_staff_title_is_set_in_exported_musicxml():
    """Without an explicit title, music21 exports a placeholder
    "Music21 Fragment" title instead of the real song title."""
    notes = [NoteEvent(start=0.0, end=0.5, pitch=60)]
    score = notes_to_grand_staff(notes, title="Clair de Lune")

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_title.musicxml"
        export_musicxml(score, output_path)
        xml = output_path.read_text()

    assert "<work-title>Clair de Lune</work-title>" in xml
    assert "Music21 Fragment" not in xml


def test_grand_staff_with_no_title_falls_back_to_music21_default():
    """No title provided -> no crash; music21's own default stands."""
    notes = [NoteEvent(start=0.0, end=0.5, pitch=60)]
    score = notes_to_grand_staff(notes)
    assert score.metadata is None or score.metadata.title is None


def test_sustained_low_melody_run_gets_temporary_bass_clef():
    """A melody that dips into the bass register for a sustained run should
    get a temporary bass clef there, then switch back — never reassigned
    to the left hand, only redrawn with a different clef."""
    low_pitches = [40, 41, 42, 43, 44]  # 5 consecutive low notes (>= MIN_CLEF_CHANGE_RUN)
    notes = [
        NoteEvent(start=i * 0.5, end=i * 0.5 + 0.5, pitch=p) for i, p in enumerate(low_pitches)
    ] + [NoteEvent(start=2.5, end=3.0, pitch=72)]  # back to normal register

    score = notes_to_grand_staff(notes)
    rh, lh = get_hand_parts(score)

    # All notes are lone onsets, so all are melody -> all stay in RH.
    assert [n.pitch.midi for n in rh.flatten().notes] == low_pitches + [72]

    clefs = sorted(rh.getElementsByClass(clef.Clef), key=lambda c: c.offset)
    assert len(clefs) == 2
    assert clefs[0].sign == "F" and clefs[0].offset == 0
    assert clefs[1].sign == "G" and clefs[1].offset == 5.0


def test_brief_low_dip_in_melody_does_not_trigger_clef_change():
    """A single passing low tone shouldn't cause a clef change — only a
    sustained run does."""
    notes = [
        NoteEvent(start=0.0, end=0.5, pitch=72),
        NoteEvent(start=0.5, end=1.0, pitch=40),  # brief dip, only 1 note
        NoteEvent(start=1.0, end=1.5, pitch=72),
    ]
    score = notes_to_grand_staff(notes)
    rh, lh = get_hand_parts(score)

    clefs = list(rh.getElementsByClass(clef.Clef))
    assert len(clefs) == 1
    assert clefs[0].sign == "G"


def test_sustained_high_accompaniment_run_gets_temporary_treble_clef():
    """Symmetric case: a left-hand accompaniment sustained in a high
    register gets a temporary treble clef, then switches back."""
    notes = []
    for i in range(5):
        t = i * 0.5
        notes.append(NoteEvent(start=t, end=t + 0.5, pitch=80))  # melody -> RH
        notes.append(NoteEvent(start=t, end=t + 0.5, pitch=68))  # accompaniment -> LH, high register
    # one more onset where the accompaniment drops back to normal register
    notes.append(NoteEvent(start=2.5, end=3.0, pitch=80))
    notes.append(NoteEvent(start=2.5, end=3.0, pitch=40))

    score = notes_to_grand_staff(notes)
    rh, lh = get_hand_parts(score)

    assert [n.pitch.midi for n in lh.flatten().notes] == [68, 68, 68, 68, 68, 40]

    clefs = sorted(lh.getElementsByClass(clef.Clef), key=lambda c: c.offset)
    assert len(clefs) == 2
    assert clefs[0].sign == "G" and clefs[0].offset == 0
    assert clefs[1].sign == "F" and clefs[1].offset == 5.0


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
