from typing import Optional

import numpy as np

from app.chords.key import is_diatonic
from app.chords.templates import BASE_TRIAD, TEMPLATES

# A plain triad's chroma also partially matches its own 7th-chord
# superset template (3 of the 7th's 4 tones are already present) — this
# caused spurious 7th-chord flicker during the Phase 0 spike. A 7th
# quality only wins over its corresponding triad (same root) if it's more
# than this much more similar.
SEVENTH_MARGIN = 0.05
# A small nudge — enough to break a close tie toward a chord that
# actually fits the song's detected key, not enough to override a
# clearly better chroma match (a genuine borrowed/chromatic chord).
DIATONIC_BONUS = 0.05


def match_chord(chroma_vector: np.ndarray, key: Optional[tuple[int, str]] = None) -> tuple[int, str]:
    """Match a 12-bin chroma vector to the closest (root, quality) chord
    template by cosine similarity, optionally biased toward chords
    diatonic to a given key."""
    norm = np.linalg.norm(chroma_vector)
    normalized = chroma_vector / norm if norm > 0 else chroma_vector

    similarities = {}
    for key_, template in TEMPLATES.items():
        score = float(np.dot(normalized, template))
        if key is not None and is_diatonic(*key_, key):
            score += DIATONIC_BONUS
        similarities[key_] = score

    best_key = max(similarities, key=similarities.get)
    best_root, best_quality = best_key

    base_triad = BASE_TRIAD.get(best_quality)
    if base_triad is not None:
        triad_similarity = similarities[(best_root, base_triad)]
        if similarities[best_key] - triad_similarity <= SEVENTH_MARGIN:
            return best_root, base_triad

    return best_root, best_quality
