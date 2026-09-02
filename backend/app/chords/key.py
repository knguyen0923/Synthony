import numpy as np

from app.chords.templates import BASE_TRIAD

# Krumhansl-Kessler key profiles — standard, published empirical
# constants from music cognition research (relative perceived
# "fit" of each pitch class to a major/minor tonal center), used
# here via correlation against a song's overall chroma distribution
# to estimate its key.
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# Expected triad quality at each diatonic scale degree (0-indexed
# semitone offset from the tonic), for major and natural-minor keys —
# the standard classical/pop harmony convention (I-ii-iii-IV-V-vi-vii°
# in major; i-ii°-III-iv-v-VI-VII in natural minor).
MAJOR_DIATONIC_QUALITIES = {0: "major", 2: "minor", 4: "minor", 5: "major", 7: "major", 9: "minor", 11: "dim"}
MINOR_DIATONIC_QUALITIES = {0: "minor", 2: "dim", 3: "major", 5: "minor", 7: "minor", 8: "major", 10: "major"}


def detect_key(chroma: np.ndarray) -> tuple[int, str]:
    """Estimate a song's key (tonic pitch class, mode) from its overall
    chroma distribution via Krumhansl-Schmuckler key-profile
    correlation: try every (tonic, mode) combination and pick whichever
    rotated profile correlates best with the song's actual pitch-class
    usage."""
    overall = chroma.mean(axis=1)
    best_score = -np.inf
    best_key = (0, "major")
    for tonic in range(12):
        for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            rotated = np.roll(profile, tonic)
            score = float(np.corrcoef(overall, rotated)[0, 1])
            if score > best_score:
                best_score = score
                best_key = (tonic, mode)
    return best_key


def is_diatonic(root: int, quality: str, key: tuple[int, str]) -> bool:
    """Whether (root, quality) is a plausible diatonic chord in `key`."""
    tonic, mode = key
    degree = (root - tonic) % 12
    table = MAJOR_DIATONIC_QUALITIES if mode == "major" else MINOR_DIATONIC_QUALITIES
    expected = table.get(degree)
    if expected is None:
        return False
    triad_quality = BASE_TRIAD.get(quality, quality)
    return triad_quality == expected
