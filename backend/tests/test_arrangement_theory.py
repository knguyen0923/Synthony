from app.arrangement.theory import (
    chord_tones,
    pitch_class_to_midi_in_range,
    stack_above,
)


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
