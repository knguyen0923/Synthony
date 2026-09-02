from music21 import clef, note, stream

from app.arrangement.theory import pitch_class_to_midi_in_range
from app.arrangement.types import ChordSymbol
from app.notation.hand_split import SECONDS_PER_QUARTER

EASY_LH_RANGE = (36, 48)  # C2-C3, matches difficulty/easy.py's LH range


def to_easy_lh(chords: list[ChordSymbol]) -> stream.Part:
    """One root note per chord, held for the chord's full duration."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    for chord in chords:
        offset = chord.start / SECONDS_PER_QUARTER
        length = chord.duration / SECONDS_PER_QUARTER
        midi = pitch_class_to_midi_in_range(chord.root, *EASY_LH_RANGE)
        n = note.Note()
        n.pitch.midi = midi
        n.duration.quarterLength = length
        part.insert(offset, n)
    return part
