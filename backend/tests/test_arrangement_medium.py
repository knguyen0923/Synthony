from app.arrangement.medium import to_medium_lh
from app.arrangement.types import ChordSymbol


def test_medium_lh_voices_a_close_position_triad():
    chords = [ChordSymbol(start=0.0, duration=1.0, root=0, quality="major")]
    part = to_medium_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.pitch.midi)
    assert [n.pitch.midi for n in notes] == [36, 40, 43]  # C2, E2, G2


def test_medium_lh_drops_the_seventh_to_stay_a_triad():
    chords = [ChordSymbol(start=0.0, duration=1.0, root=0, quality="dom7")]
    part = to_medium_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.pitch.midi)
    assert len(notes) == 3
    assert [n.pitch.midi for n in notes] == [36, 40, 43]  # root/3rd/5th only


def test_medium_lh_respects_a_non_default_tempo():
    chords = [ChordSymbol(start=0.0, duration=2.0, root=0, quality="major")]
    part = to_medium_lh(chords, seconds_per_quarter=1.0)
    notes = list(part.flatten().notes)
    assert notes[0].duration.quarterLength == 2.0  # vs 4.0 at the default tempo
