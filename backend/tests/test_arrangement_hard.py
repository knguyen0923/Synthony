from app.arrangement.hard import to_hard_lh
from app.arrangement.types import ChordSymbol


def test_hard_lh_uses_a_full_block_chord_for_a_short_chord():
    # duration=0.5s is below SHORT_CHORD_THRESHOLD — a chopped-off arpeggio
    # would sound worse than one clean block-chord hit here
    chords = [ChordSymbol(start=0.0, duration=0.5, root=0, quality="major")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.pitch.midi)
    assert [n.pitch.midi for n in notes] == [36, 40, 43]  # C2, E2, G2 — full triad at once
    assert all(n.offset == 0.0 for n in notes)


def test_hard_lh_includes_the_seventh_in_a_short_chords_block_chord():
    chords = [ChordSymbol(start=0.0, duration=0.5, root=0, quality="dom7")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.pitch.midi)
    assert [n.pitch.midi for n in notes] == [36, 40, 43, 46]  # C2, E2, G2, Bb2 — 7th included


def test_hard_lh_arpeggiates_root_then_fifth_across_a_long_chord():
    # duration=3.0s is above SHORT_CHORD_THRESHOLD — long enough to arpeggiate
    chords = [ChordSymbol(start=0.0, duration=3.0, root=0, quality="major")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    assert [n.pitch.midi for n in notes[:4]] == [36, 43, 40, 43]  # root, 5th, 3rd, 5th
