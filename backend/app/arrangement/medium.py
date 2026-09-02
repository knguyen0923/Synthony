from music21 import clef, note, stream

from app.arrangement.theory import (
    ROOT_VELOCITY,
    INNER_VOICE_VELOCITY,
    lh_voicing,
    pitch_class_to_midi_in_range,
    quantized_duration,
    round_to_grid,
    stack_above,
)
from app.arrangement.types import ChordSymbol
from app.notation.hand_split import SECONDS_PER_QUARTER

MEDIUM_LH_RANGE = (36, 55)  # C2-G3, matches difficulty/medium.py's LH range
MAX_BLOCK_TONES = 3  # root + third + fifth; drop the 7th for playability


def to_medium_lh(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """A close-position block chord (root + third + fifth) per chord,
    held for the chord's full duration."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    for chord in chords:
        all_tones, _ = lh_voicing(chord, seconds_per_quarter)
        tones = all_tones[:MAX_BLOCK_TONES]
        offset = round_to_grid(chord.start / seconds_per_quarter)
        length = quantized_duration(chord.duration, seconds_per_quarter)
        root_midi = pitch_class_to_midi_in_range(tones[0], *MEDIUM_LH_RANGE)
        for pitch_class in tones:
            n = note.Note()
            n.pitch.midi = stack_above(root_midi, pitch_class)
            n.duration.quarterLength = length
            n.volume.velocityScalar = ROOT_VELOCITY if pitch_class == tones[0] else INNER_VOICE_VELOCITY
            part.insert(offset, n)
    return part
