import copy

from music21 import stream

from app.notation.hand_split import carry_clef


def shift_into_range(part: stream.Part, low: int, high: int) -> stream.Part:
    """Octave-shift each note's pitch, preserving pitch class, until its
    MIDI number falls within [low, high]."""
    shifted = stream.Part(id=part.id)

    for element in part.flatten().notes:
        new_element = copy.deepcopy(element)
        midi = new_element.pitch.midi
        while midi < low:
            midi += 12
        while midi > high:
            midi -= 12
        new_element.pitch.midi = midi
        shifted.insert(element.offset, new_element)

    carry_clef(part, shifted)
    return shifted
