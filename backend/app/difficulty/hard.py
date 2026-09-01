import copy

from music21 import stream


def to_hard(score: stream.Score) -> stream.Score:
    """Passthrough — Hard tier is the melody-split, grand-staff score as
    is, with no simplification."""
    return copy.deepcopy(score)
