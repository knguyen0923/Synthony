from music21 import clef, note, stream

from app.arrangement.theory import (
    ROOT_VELOCITY,
    INNER_VOICE_VELOCITY,
    chord_tones,
    pitch_class_to_midi_in_range,
    quantized_duration,
    round_to_grid,
    stack_above,
)
from app.arrangement.types import ChordSymbol
from app.notation.hand_split import SECONDS_PER_QUARTER

HARD_LH_RANGE = (36, 55)  # C2-G3, same bass register as the Medium tier
ARPEGGIO_STEP = 0.5  # eighth note, in quarterLength units
# Classic Alberti-bass order: root, fifth, third, fifth (indices into
# chord_tones()'s root-first ordering). The inner `% len(tones)` handles
# chords with fewer tones than the pattern references.
ALBERTI_INDICES = (0, 2, 1, 2)
# A chord shorter than this (tempo-relative, not a fixed number of
# seconds) gets a single block-chord hit (full tone set, including the
# 7th) instead of an arpeggio — an Alberti pattern chopped off partway
# through a short chord reads worse than one clean stab. 1.5 bars in 4/4
# (matches this codebase's fixed-4/4 assumption). A fixed-seconds
# threshold made this split accidentally tempo-dependent: a slow song's
# bars were all longer than the fixed cutoff (100% arpeggio, zero
# block-chord variety), while a fast song's threshold happened to land
# almost exactly between its 1-bar and 2-bar chords purely by
# coincidence (found via real-song testing).
SHORT_CHORD_QUARTER_LENGTH = 6.0
# On a long-held chord, repeating the same 4-note Alberti cycle unchanged
# reads as "the same chord playing over and over" — every Nth cycle lifts
# an octave for variety. Short/normal-length chords rarely reach a second
# cycle at all, so this only kicks in on genuinely long holds.
CYCLES_BETWEEN_OCTAVE_LIFTS = 4


def _short_chord_threshold(seconds_per_quarter: float) -> float:
    """Real-seconds duration below which a chord is "short" (gets a block
    chord instead of an arpeggio) at the given tempo — 1.5 bars."""
    return SHORT_CHORD_QUARTER_LENGTH * seconds_per_quarter


def to_hard_lh(chords: list[ChordSymbol], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """A full block chord for short chords, an Alberti-bass arpeggio
    (root-fifth-third-fifth, subdivided into eighth notes) for longer
    ones — variety instead of one repeating pattern regardless of
    context."""
    part = stream.Part(id="LH")
    part.insert(0, clef.BassClef())
    step_seconds = ARPEGGIO_STEP * seconds_per_quarter
    short_chord_threshold = _short_chord_threshold(seconds_per_quarter)

    for chord in chords:
        tones = chord_tones(chord.root, chord.quality)
        root_midi = pitch_class_to_midi_in_range(tones[0], *HARD_LH_RANGE)

        if chord.duration < short_chord_threshold:
            offset = round_to_grid(chord.start / seconds_per_quarter)
            length = quantized_duration(chord.duration, seconds_per_quarter)
            for pitch_class in tones:
                n = note.Note()
                n.pitch.midi = stack_above(root_midi, pitch_class)
                n.duration.quarterLength = length
                n.volume.velocityScalar = ROOT_VELOCITY if pitch_class == tones[0] else INNER_VOICE_VELOCITY
                part.insert(offset, n)
            continue

        step = 0
        elapsed = 0.0
        while elapsed < chord.duration:
            cycle = step // len(ALBERTI_INDICES)
            index = ALBERTI_INDICES[step % len(ALBERTI_INDICES)] % len(tones)
            pitch_class = tones[index]
            offset = round_to_grid((chord.start + elapsed) / seconds_per_quarter)
            octave_lift = 12 if cycle % CYCLES_BETWEEN_OCTAVE_LIFTS == CYCLES_BETWEEN_OCTAVE_LIFTS - 1 else 0

            n = note.Note()
            n.pitch.midi = stack_above(root_midi, pitch_class) + octave_lift
            n.duration.quarterLength = ARPEGGIO_STEP
            n.volume.velocityScalar = ROOT_VELOCITY if index == 0 else INNER_VOICE_VELOCITY
            part.insert(offset, n)

            step += 1
            elapsed += step_seconds

    return part
