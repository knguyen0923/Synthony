from app.arrangement.theory import (
    chord_tones,
    lh_voicing,
    pitch_class_to_midi_in_range,
    short_chord_threshold,
    stack_above,
)
from app.arrangement.types import ChordSymbol


def test_chord_tones_major():
    assert chord_tones(0, "major") == [0, 4, 7]  # C major: C E G


def test_chord_tones_min7_wraps_pitch_class():
    assert chord_tones(2, "min7") == [2, 5, 9, 0]  # Dmin7: D F A C


def test_pitch_class_to_midi_in_range_shifts_up_and_down():
    assert pitch_class_to_midi_in_range(0, 36, 48) == 36  # C -> C2
    assert pitch_class_to_midi_in_range(11, 36, 48) == 47  # B -> B2


def test_stack_above_finds_nearest_instance_at_or_above_base():
    assert stack_above(36, 4) == 40  # E above C2 -> E2
    assert stack_above(36, 0) == 36  # same pitch class as base, no shift needed


def test_short_chord_threshold_is_one_and_a_half_bars_at_the_given_tempo():
    import pytest
    seconds_per_quarter = 0.5
    assert short_chord_threshold(seconds_per_quarter) == pytest.approx(6.0 * 0.5)


def test_short_chord_threshold_scales_with_tempo():
    fast_tempo = short_chord_threshold(60.0 / 129.2)
    slow_tempo = short_chord_threshold(60.0 / 73.8)
    assert slow_tempo > fast_tempo


def test_lh_voicing_returns_chord_tones_root_first():
    chord = ChordSymbol(start=0.0, duration=1.0, root=2, quality="min7")
    tones, _ = lh_voicing(chord, seconds_per_quarter=0.5)
    assert tones == chord_tones(2, "min7")


def test_lh_voicing_is_short_below_threshold():
    chord = ChordSymbol(start=0.0, duration=0.5, root=0, quality="major")
    _, is_short = lh_voicing(chord, seconds_per_quarter=0.5)
    assert is_short is True


def test_lh_voicing_is_not_short_at_or_above_threshold():
    chord = ChordSymbol(start=0.0, duration=6.0, root=0, quality="major")
    _, is_short = lh_voicing(chord, seconds_per_quarter=1.0)
    assert is_short is False
