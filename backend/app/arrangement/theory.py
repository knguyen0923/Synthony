CHORD_INTERVALS: dict[str, tuple[int, ...]] = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "dim": (0, 3, 6),
    "dom7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
}


def chord_tones(root: int, quality: str) -> list[int]:
    """Pitch classes (0-11), root first, that make up the chord."""
    return [(root + interval) % 12 for interval in CHORD_INTERVALS[quality]]


def pitch_class_to_midi_in_range(pitch_class: int, low: int, high: int) -> int:
    """Lowest MIDI number with the given pitch class that falls within
    [low, high]."""
    midi = pitch_class
    while midi < low:
        midi += 12
    while midi > high:
        midi -= 12
    return midi


def stack_above(base_midi: int, pitch_class: int) -> int:
    """Smallest MIDI number >= base_midi with the given pitch class —
    voices a chord tone in close position above an anchor note."""
    midi = pitch_class + 12 * (base_midi // 12)
    while midi < base_midi:
        midi += 12
    return midi
