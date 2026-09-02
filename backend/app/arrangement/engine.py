from dataclasses import dataclass

from music21 import stream

from app.arrangement.easy import to_easy_lh
from app.arrangement.hard import to_hard_lh
from app.arrangement.medium import to_medium_lh
from app.arrangement.types import ChordSymbol


@dataclass
class ArrangementVariants:
    easy: stream.Part
    medium: stream.Part
    hard: stream.Part


def generate_lh_variants(chords: list[ChordSymbol]) -> ArrangementVariants:
    return ArrangementVariants(
        easy=to_easy_lh(chords),
        medium=to_medium_lh(chords),
        hard=to_hard_lh(chords),
    )
