from dataclasses import dataclass


@dataclass(frozen=True)
class NoteEvent:
    start: float       # seconds
    end: float         # seconds
    pitch: int         # MIDI note number, 0-127
    velocity: float = 0.8  # 0.0-1.0
