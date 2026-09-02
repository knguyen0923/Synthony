from app.arrangement.hard import to_hard_lh
from app.arrangement.types import ChordSymbol


def test_hard_lh_arpeggiates_root_then_fifth_across_one_beat():
    # duration=0.5s = 1 quarter note = 2 eighth-note arpeggio steps
    chords = [ChordSymbol(start=0.0, duration=0.5, root=0, quality="major")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    assert [n.offset for n in notes] == [0.0, 0.5]
    assert [n.pitch.midi for n in notes] == [36, 43]  # root(C2), fifth(G2)


def test_hard_lh_continues_alberti_pattern_into_third_and_fourth_steps():
    # duration=1.0s = 2 quarter notes = 4 eighth-note arpeggio steps
    chords = [ChordSymbol(start=0.0, duration=1.0, root=0, quality="major")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    assert [n.pitch.midi for n in notes] == [36, 43, 40, 43]  # root, 5th, 3rd, 5th
