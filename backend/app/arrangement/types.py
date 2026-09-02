from dataclasses import dataclass


@dataclass(frozen=True)
class ChordSymbol:
    start: float       # seconds
    duration: float     # seconds
    root: int           # pitch class, 0=C .. 11=B
    quality: str         # one of theory.CHORD_INTERVALS' keys
