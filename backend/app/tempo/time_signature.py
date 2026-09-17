"""Time-signature detection: distinguishes 3/4 from 4/4 (the two most
common cases for pop/rock/classical repertoire) using madmom's joint
beat+downbeat tracker. Other meters (2/4, 6/8, ...) are explicitly out of
scope -- ambiguous or inconsistent detection falls back to 4/4, matching
the pipeline's previous (implicit, undetected) behavior.
"""
from __future__ import annotations

from collections import Counter
from typing import List, Optional

from music21 import meter

from app.tempo.detect import _MADMOM_FPS, _madmom_import_lock, _numpy_legacy_aliases, has_audible_signal

_CANDIDATE_BEATS_PER_BAR = [3, 4]
_MIN_BARS = 4
_MIN_AGREEMENT = 0.90
_DEFAULT_TIME_SIGNATURE = "4/4"


def _bar_lengths_from_downbeats(beat_positions: List[int]) -> List[int]:
    """beat_positions: madmom's 1-indexed position-within-bar for each
    detected beat (e.g. [4, 1, 2, 3, 4, 1, 2, 3, 4] for two 4/4 bars after
    a partial leading bar). Returns one length per *complete* bar (from
    one downbeat to the next) -- a leading partial bar (before the first
    downbeat) and a trailing partial bar (after the last downbeat, with no
    following downbeat to close it) are both excluded since their true
    length can't be determined."""
    downbeat_indices = [i for i, pos in enumerate(beat_positions) if pos == 1]
    return [end - start for start, end in zip(downbeat_indices, downbeat_indices[1:])]


def _consistent_bar_length(
    bar_lengths: List[int], min_bars: int = _MIN_BARS, min_agreement: float = _MIN_AGREEMENT
) -> Optional[int]:
    """The modal bar length, if at least `min_bars` complete bars were
    found and at least `min_agreement` of them share that length.
    Otherwise None (caller should fall back to the default)."""
    if len(bar_lengths) < min_bars:
        return None
    mode_length, mode_count = Counter(bar_lengths).most_common(1)[0]
    if mode_count / len(bar_lengths) >= min_agreement:
        return mode_length
    return None


def detect_time_signature(audio_path: str) -> meter.TimeSignature:
    """Detects whether `audio_path` is in 3/4 or 4/4 using madmom's
    RNNDownBeatProcessor + DBNDownBeatTrackingProcessor. Falls back to
    4/4 on near-silent audio, any madmom failure, too few detected bars,
    or inconsistent bar-length agreement -- always returns a usable
    TimeSignature, never raises."""
    if not has_audible_signal(audio_path):
        return meter.TimeSignature(_DEFAULT_TIME_SIGNATURE)

    try:
        with _madmom_import_lock, _numpy_legacy_aliases():
            from madmom.features.downbeats import DBNDownBeatTrackingProcessor, RNNDownBeatProcessor

            activations = RNNDownBeatProcessor()(audio_path)
            result = DBNDownBeatTrackingProcessor(beats_per_bar=_CANDIDATE_BEATS_PER_BAR, fps=_MADMOM_FPS)(
                activations
            )
        beat_positions = [int(round(position)) for position in result[:, 1]]
    except Exception:
        return meter.TimeSignature(_DEFAULT_TIME_SIGNATURE)

    bar_lengths = _bar_lengths_from_downbeats(beat_positions)
    detected = _consistent_bar_length(bar_lengths)
    if detected is None:
        return meter.TimeSignature(_DEFAULT_TIME_SIGNATURE)
    return meter.TimeSignature(f"{detected}/4")
