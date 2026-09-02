from app.notation.hand_split import NOTATION_GRID

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


def round_to_grid(value: float) -> float:
    """Round a value (in quarterLength units) to the nearest NOTATION_GRID
    step. Chord timings come from real beat-tracking — irregular floats
    like 1.869206349206349s — and without this, the quarterLength values
    derived from them (e.g. 256/3675) aren't expressible in MusicXML,
    which requires app.notation.hand_split's same grid constraint."""
    return round(value / NOTATION_GRID) * NOTATION_GRID


def quantized_duration(seconds: float, seconds_per_quarter: float) -> float:
    """Convert a duration in seconds to a MusicXML-safe quarterLength:
    floored at one grid step (never zero-length) and rounded to the
    grid."""
    quarter_length = max(seconds / seconds_per_quarter, NOTATION_GRID)
    return round_to_grid(quarter_length)
