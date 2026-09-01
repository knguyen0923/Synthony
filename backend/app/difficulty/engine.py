from dataclasses import dataclass

from music21 import stream

from app.difficulty.easy import to_easy
from app.difficulty.medium import to_medium
from app.difficulty.hard import to_hard


@dataclass
class DifficultyVariants:
    easy: stream.Score
    medium: stream.Score
    hard: stream.Score


def generate_variants(score: stream.Score) -> DifficultyVariants:
    return DifficultyVariants(
        easy=to_easy(score),
        medium=to_medium(score),
        hard=to_hard(score),
    )
