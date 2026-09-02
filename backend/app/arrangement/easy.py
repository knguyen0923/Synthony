from music21 import clef, note, stream

from app.arrangement.theory import ROOT_VELOCITY, pitch_class_to_midi_in_range, quantized_duration, round_to_grid
from app.arrangement.types import ChordSymbol
from app.notation.hand_split import SECONDS_PER_QUARTER

EASY_LH_RANGE = (36, 48)  # C2-C3, matches difficulty/easy.py's LH range


def to_easy_lh(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """One root note per chord, held for the chord's full duration."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    for chord in chords:
        offset = round_to_grid(chord.start / seconds_per_quarter)
        length = quantized_duration(chord.duration, seconds_per_quarter)
        midi = pitch_class_to_midi_in_range(chord.root, *EASY_LH_RANGE)
        n = note.Note()
        n.pitch.midi = midi
        n.duration.quarterLength = length
        n.volume.velocityScalar = ROOT_VELOCITY
        part.insert(offset, n)
    return part
