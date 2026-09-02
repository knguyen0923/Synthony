import pytest

from app.arrangement.types import ChordSymbol
from app.chords.detect import (
    _absorb_short_chords,
    _merge_consecutive,
    _min_chord_duration,
    _tempo_to_seconds_per_quarter,
    detect_chords,
)


def test_tempo_to_seconds_per_quarter_converts_bpm():
    assert _tempo_to_seconds_per_quarter(120.0) == 0.5
    assert _tempo_to_seconds_per_quarter(60.0) == 1.0


def test_tempo_to_seconds_per_quarter_clamps_extreme_values():
    assert _tempo_to_seconds_per_quarter(20.0) == 60.0 / 60.0   # clamped up to MIN_TEMPO_BPM
    assert _tempo_to_seconds_per_quarter(500.0) == 60.0 / 200.0  # clamped down to MAX_TEMPO_BPM


def test_tempo_to_seconds_per_quarter_falls_back_on_zero_or_none():
    assert _tempo_to_seconds_per_quarter(0.0) == 0.5
    assert _tempo_to_seconds_per_quarter(None) == 0.5


def test_min_chord_duration_is_half_a_bar_at_the_given_tempo():
    seconds_per_quarter = 60.0 / 129.2  # a real detected tempo (129.2 BPM)
    assert _min_chord_duration(seconds_per_quarter) == pytest.approx(0.5 * 4 * seconds_per_quarter)


def test_min_chord_duration_always_stays_below_a_full_bar():
    # Real bug, found by inspecting real-song output: the old threshold
    # was a fixed 2.0 seconds regardless of tempo. At 129.2 BPM a full bar
    # is only ~1.86s — shorter than that fixed threshold — so nearly
    # every legitimate single-bar chord was absorbed into whatever came
    # before it, chaining into a runaway merge that flatlined a real
    # alternating progression onto one chord for an entire 45-second clip.
    # A tempo-relative threshold must always stay below one full bar, at
    # any tempo, so a real bar-length chord is never mistaken for a blip.
    for bpm in (60.0, 90.0, 120.0, 129.2, 160.0, 200.0):
        seconds_per_quarter = 60.0 / bpm
        bar_length = 4 * seconds_per_quarter
        assert _min_chord_duration(seconds_per_quarter) < bar_length


def test_absorb_short_chords_merges_a_short_chord_into_the_previous_one():
    chords = [
        ChordSymbol(start=0.0, duration=2.0, root=0, quality="major"),
        ChordSymbol(start=2.0, duration=0.2, root=9, quality="minor"),  # a blip — below MIN_CHORD_DURATION
        ChordSymbol(start=2.2, duration=2.0, root=7, quality="major"),
    ]
    result = _absorb_short_chords(chords, min_duration=1.0)
    assert result == [
        ChordSymbol(start=0.0, duration=2.2, root=0, quality="major"),
        ChordSymbol(start=2.2, duration=2.0, root=7, quality="major"),
    ]


def test_absorb_short_chords_merges_a_leading_short_chord_into_the_next_one():
    chords = [
        ChordSymbol(start=0.0, duration=0.1, root=9, quality="minor"),  # blip with no previous chord
        ChordSymbol(start=0.1, duration=2.0, root=0, quality="major"),
    ]
    result = _absorb_short_chords(chords, min_duration=1.0)
    assert result == [ChordSymbol(start=0.0, duration=2.1, root=0, quality="major")]


def test_absorb_short_chords_leaves_a_single_short_chord_as_is():
    chords = [ChordSymbol(start=0.0, duration=0.1, root=0, quality="major")]
    assert _absorb_short_chords(chords, min_duration=1.0) == chords


def test_absorb_short_chords_does_not_flatline_a_fast_tempo_alternating_progression():
    # Real bug, found by inspecting real-song output: at 129 BPM (a real
    # detected tempo), a full bar is ~1.86s — shorter than the old fixed
    # 2.0s absolute-seconds threshold, which absorbed every single
    # legitimate bar-length chord into whatever came before it, chaining
    # into a runaway merge that flatlined a real alternating progression
    # onto one chord for the whole clip. A tempo-relative threshold (half
    # a bar) must keep legitimate bar-length chords separate.
    seconds_per_quarter = 60.0 / 129.2
    bar_length = 4 * seconds_per_quarter
    min_duration = 0.5 * bar_length
    chords = [
        ChordSymbol(
            start=i * bar_length,
            duration=bar_length,
            root=3 if i % 2 == 0 else 0,
            quality="major" if i % 2 == 0 else "min7",
        )
        for i in range(10)
    ]
    result = _absorb_short_chords(chords, min_duration=min_duration)
    assert len(result) == 10  # every bar-length chord survives, none absorbed


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


def test_detect_chords_returns_a_sequence_and_tempo_covering_the_clip(synthetic_piano_wav):
    chords, seconds_per_quarter, key = detect_chords(str(synthetic_piano_wav))

    assert len(chords) >= 1
    assert chords[0].start == 0.0
    assert chords[-1].start + chords[-1].duration <= 2.5  # clip is 2s, allow rounding slack
    for chord in chords:
        assert 0 <= chord.root <= 11
        assert chord.quality in ("major", "minor", "dim", "dom7", "maj7", "min7")
    assert seconds_per_quarter > 0
    tonic, mode = key
    assert 0 <= tonic <= 11
    assert mode in ("major", "minor")


def test_detect_chords_still_returns_a_sequence_and_tempo_with_key_bias_wired_in(synthetic_piano_wav):
    # Regression check: wiring in key detection must not break the
    # existing contract (this duplicates the shape of the existing
    # tempo-covering test deliberately, as a belt-and-suspenders check
    # that detect_chords's key-detection call doesn't raise on real
    # audio input).
    chords, seconds_per_quarter, key = detect_chords(str(synthetic_piano_wav))
    assert len(chords) >= 1
    assert seconds_per_quarter > 0
