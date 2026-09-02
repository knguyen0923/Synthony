from app.arrangement.types import ChordSymbol
from app.chords.detect import _merge_consecutive, detect_chords


def test_merge_consecutive_combines_matching_adjacent_chords():
    chords = [
        ChordSymbol(start=0.0, duration=2.0, root=0, quality="major"),
        ChordSymbol(start=2.0, duration=2.0, root=0, quality="major"),
        ChordSymbol(start=4.0, duration=2.0, root=7, quality="major"),
    ]
    merged = _merge_consecutive(chords)
    assert merged == [
        ChordSymbol(start=0.0, duration=4.0, root=0, quality="major"),
        ChordSymbol(start=4.0, duration=2.0, root=7, quality="major"),
    ]


def test_detect_chords_returns_a_sequence_covering_the_clip(synthetic_piano_wav):
    chords = detect_chords(str(synthetic_piano_wav))

    assert len(chords) >= 1
    assert chords[0].start == 0.0
    assert chords[-1].start + chords[-1].duration <= 2.5  # clip is 2s, allow rounding slack
    for chord in chords:
        assert 0 <= chord.root <= 11
        assert chord.quality in ("major", "minor", "dim", "dom7", "maj7", "min7")
