from music21 import clef, note, stream

from app.arrangement.theory import chord_tones, pitch_class_to_midi_in_range, round_to_grid, stack_above
from app.arrangement.types import ChordSymbol
from app.notation.hand_split import SECONDS_PER_QUARTER

HARD_LH_RANGE = (36, 55)  # C2-G3, same bass register as the Medium tier
ARPEGGIO_STEP = 0.5  # eighth note, in quarterLength units
# Classic Alberti-bass order: root, fifth, third, fifth (indices into
# chord_tones()'s root-first ordering). The inner `% len(tones)` handles
# chords with fewer tones than the pattern references.
ALBERTI_INDICES = (0, 2, 1, 2)


def to_hard_lh(chords: list[ChordSymbol]) -> stream.Part:
    """An Alberti-bass arpeggio (root-fifth-third-fifth) per chord,
    subdivided into eighth notes across the chord's duration."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    step_seconds = ARPEGGIO_STEP * SECONDS_PER_QUARTER

    for chord in chords:
        tones = chord_tones(chord.root, chord.quality)
        root_midi = pitch_class_to_midi_in_range(tones[0], *HARD_LH_RANGE)

        step = 0
        elapsed = 0.0
        while elapsed < chord.duration:
            index = ALBERTI_INDICES[step % len(ALBERTI_INDICES)] % len(tones)
            pitch_class = tones[index]
            offset = round_to_grid((chord.start + elapsed) / SECONDS_PER_QUARTER)

            n = note.Note()
            n.pitch.midi = stack_above(root_midi, pitch_class)
            n.duration.quarterLength = ARPEGGIO_STEP
            part.insert(offset, n)

            step += 1
            elapsed += step_seconds

    return part
