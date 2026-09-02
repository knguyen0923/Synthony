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
