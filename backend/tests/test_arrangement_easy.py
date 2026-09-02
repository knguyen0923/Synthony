import pytest

from app.arrangement.easy import to_easy_lh
from app.arrangement.theory import ROOT_VELOCITY
from app.arrangement.types import ChordSymbol


def test_easy_lh_holds_root_for_full_chord_duration():
    chords = [ChordSymbol(start=0.0, duration=2.0, root=0, quality="major")]
    part = to_easy_lh(chords)
    notes = list(part.flatten().notes)
    assert len(notes) == 1
    assert notes[0].pitch.midi == 36  # C2, nearest C within (36, 48)
    assert notes[0].duration.quarterLength == 4.0  # 2s / 0.5s-per-quarter


def test_easy_lh_places_each_chord_at_its_own_offset():
    chords = [
        ChordSymbol(start=0.0, duration=1.0, root=0, quality="major"),
        ChordSymbol(start=1.0, duration=1.0, root=7, quality="major"),
    ]
    part = to_easy_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    assert [n.offset for n in notes] == [0.0, 2.0]
    assert notes[1].pitch.midi == 43  # G2, nearest G within (36, 48)


def test_easy_lh_respects_a_non_default_tempo():
    chords = [ChordSymbol(start=0.0, duration=2.0, root=0, quality="major")]
    part = to_easy_lh(chords, seconds_per_quarter=1.0)  # 60 BPM instead of the 120 BPM default
    notes = list(part.flatten().notes)
    assert notes[0].duration.quarterLength == 2.0  # 2s / 1.0s-per-quarter, vs 4.0 at the default tempo


def test_easy_lh_root_note_has_root_velocity():
    chords = [ChordSymbol(start=0.0, duration=2.0, root=0, quality="major")]
    part = to_easy_lh(chords)
    n = list(part.flatten().notes)[0]
    assert n.volume.velocityScalar == pytest.approx(ROOT_VELOCITY)
