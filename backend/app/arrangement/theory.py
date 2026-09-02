from app.arrangement.types import ChordSymbol
from app.notation.hand_split import NOTATION_GRID

CHORD_INTERVALS: dict[str, tuple[int, ...]] = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "dim": (0, 3, 6),
    "dom7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
}


# A fixed, deterministic accent — not derived from any audio analysis,
# since LH notes are synthesized from chord symbols and have no
# per-note confidence data the way Basic Pitch's RH output does. Real
# pianists voice the bass/root note more prominently than inner voices;
# this is that rule, applied uniformly.
ROOT_VELOCITY = 0.75
INNER_VOICE_VELOCITY = 0.55


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


# A chord shorter than this (tempo-relative, not a fixed number of
# seconds) gets a single block-chord hit (full tone set, including the
# 7th) instead of an arpeggio — an Alberti pattern chopped off partway
# through a short chord reads worse than one clean stab. 1.5 bars in 4/4
# (matches this codebase's fixed-4/4 assumption). A fixed-seconds
# threshold made this split accidentally tempo-dependent: a slow song's
# bars were all longer than the fixed cutoff (100% arpeggio, zero
# block-chord variety), while a fast song's threshold happened to land
# almost exactly between its 1-bar and 2-bar chords purely by
# coincidence (found via real-song testing).
SHORT_CHORD_QUARTER_LENGTH = 6.0


def short_chord_threshold(seconds_per_quarter: float) -> float:
    """Real-seconds duration below which a chord is "short" (gets a block
    chord instead of an arpeggio) at the given tempo — 1.5 bars."""
    return SHORT_CHORD_QUARTER_LENGTH * seconds_per_quarter


def lh_voicing(chord: ChordSymbol, seconds_per_quarter: float) -> tuple[list[int], bool]:
    """The tones (pitch classes, root first) and short/long classification
    every LH difficulty tier is built from for one chord — the single
    source Easy/Medium/Hard all read from, so their tone choices are
    provably derived from one place rather than three independently
    authored ones. `is_short` mirrors Hard's block-chord-vs-arpeggio
    split; Easy and Medium ignore it and always render a static block."""
    tones = chord_tones(chord.root, chord.quality)
    is_short = chord.duration < short_chord_threshold(seconds_per_quarter)
    return tones, is_short
