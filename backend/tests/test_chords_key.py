import numpy as np

from app.chords.key import MAJOR_PROFILE, MINOR_PROFILE, detect_key, is_diatonic


def test_detect_key_recovers_a_rotated_major_profile():
    rotated = np.roll(MAJOR_PROFILE, 4)  # simulate a song centered on E major (tonic=4)
    chroma = rotated.reshape(12, 1)
    assert detect_key(chroma) == (4, "major")


def test_detect_key_recovers_a_rotated_minor_profile():
    rotated = np.roll(MINOR_PROFILE, 9)  # simulate a song centered on A minor (tonic=9)
    chroma = rotated.reshape(12, 1)
    assert detect_key(chroma) == (9, "minor")


def test_is_diatonic_accepts_the_tonic_major_triad_in_a_major_key():
    assert is_diatonic(0, "major", (0, "major")) is True  # I


def test_is_diatonic_accepts_the_relative_minor_in_a_major_key():
    assert is_diatonic(9, "minor", (0, "major")) is True  # vi


def test_is_diatonic_rejects_a_non_diatonic_chord():
    assert is_diatonic(1, "major", (0, "major")) is False  # bII, not diatonic to C major


def test_is_diatonic_collapses_a_seventh_to_its_triad_quality():
    assert is_diatonic(7, "dom7", (0, "major")) is True  # V7 in C major — dom7 collapses to major (V)


def test_is_diatonic_works_for_minor_keys():
    assert is_diatonic(0, "minor", (0, "minor")) is True   # i
    assert is_diatonic(5, "minor", (0, "minor")) is True   # iv
    assert is_diatonic(1, "major", (0, "minor")) is False  # not diatonic to C minor
