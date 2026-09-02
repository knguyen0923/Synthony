import numpy as np

from app.chords.key import MAJOR_PROFILE, MINOR_PROFILE, detect_key


def test_detect_key_recovers_a_rotated_major_profile():
    rotated = np.roll(MAJOR_PROFILE, 4)  # simulate a song centered on E major (tonic=4)
    chroma = rotated.reshape(12, 1)
    assert detect_key(chroma) == (4, "major")


def test_detect_key_recovers_a_rotated_minor_profile():
    rotated = np.roll(MINOR_PROFILE, 9)  # simulate a song centered on A minor (tonic=9)
    chroma = rotated.reshape(12, 1)
    assert detect_key(chroma) == (9, "minor")
