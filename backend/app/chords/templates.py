import numpy as np

from app.arrangement.theory import chord_tones

QUALITIES = ("major", "minor", "dim", "dom7", "maj7", "min7")
# Each 7th quality's corresponding triad quality (same root), used by
# match_chord's margin rule.
BASE_TRIAD: dict[str, str] = {"dom7": "major", "maj7": "major", "min7": "minor"}


def _template_vector(root: int, quality: str) -> np.ndarray:
    vector = np.zeros(12)
    for pitch_class in chord_tones(root, quality):
        vector[pitch_class] = 1.0
    return vector / np.linalg.norm(vector)


TEMPLATES: dict[tuple[int, str], np.ndarray] = {
    (root, quality): _template_vector(root, quality)
    for root in range(12)
    for quality in QUALITIES
}
