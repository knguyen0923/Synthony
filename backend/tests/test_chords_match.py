import numpy as np

from app.chords.match import match_chord


def test_match_chord_identifies_pure_c_major_triad():
    chroma = np.zeros(12)
    for pitch_class in (0, 4, 7):  # C, E, G
        chroma[pitch_class] = 1.0
    assert match_chord(chroma) == (0, "major")


def test_match_chord_identifies_a_minor_triad():
    chroma = np.zeros(12)
    for pitch_class in (9, 0, 4):  # A, C, E
        chroma[pitch_class] = 1.0
    assert match_chord(chroma) == (9, "minor")


def test_match_chord_identifies_dominant_seventh_when_clearly_present():
    chroma = np.zeros(12)
    for pitch_class in (0, 4, 7, 10):  # C dominant 7th: C E G Bb
        chroma[pitch_class] = 1.0
    assert match_chord(chroma) == (0, "dom7")


def test_match_chord_distinguishes_major_seventh_from_dominant_seventh():
    chroma = np.zeros(12)
    for pitch_class in (0, 4, 7, 11):  # C major 7th: C E G B
        chroma[pitch_class] = 1.0
    assert match_chord(chroma) == (0, "maj7")


def test_match_chord_accepts_an_optional_key_without_changing_a_clear_match():
    chroma = np.zeros(12)
    for pitch_class in (0, 4, 7):
        chroma[pitch_class] = 1.0
    # A key where C major isn't even diatonic shouldn't override an
    # unambiguous, exact chroma match.
    assert match_chord(chroma, key=(6, "major")) == (0, "major")


def test_match_chord_key_bias_does_not_break_the_no_key_default():
    chroma = np.zeros(12)
    for pitch_class in (9, 0, 4):
        chroma[pitch_class] = 1.0
    assert match_chord(chroma) == (9, "minor")
