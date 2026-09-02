import numpy as np

# Krumhansl-Kessler key profiles — standard, published empirical
# constants from music cognition research (relative perceived
# "fit" of each pitch class to a major/minor tonal center), used
# here via correlation against a song's overall chroma distribution
# to estimate its key.
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


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
