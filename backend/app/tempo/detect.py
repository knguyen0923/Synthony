"""Real beat-detection-driven tempo mapping, replacing the pipeline's old
fixed-120-BPM / fixed-32nd-note-grid assumption.

Rhythm quantization needs the *position* (in quarterLength/beats) of every
note, not just its raw timestamp in seconds. A single global BPM estimate
gets that position wrong wherever the real performance's tempo drifts even
slightly, because it forces one straight line through timing data that
isn't straight. A "beat map" -- a piecewise-linear function built directly
from a sequence of detected beat timestamps -- is correct wherever a global
BPM is not, and degrades gracefully to the same math as a fixed tempo when
there's only one interval to work with (see `BeatMap.constant`).

Beat detection itself uses madmom's neural beat tracker
(`RNNBeatProcessor` + `DBNBeatTrackingProcessor`), which is dramatically
more accurate than librosa's default `beat_track` at pinning down *where*
each beat actually falls -- see `_run_madmom_beat_tracking` and the
`_numpy_legacy_aliases` shim below for why that library needs help to even
import under numpy 2.x.
"""

import bisect
import threading
from contextlib import contextmanager

import librosa
import numpy as np

# Matches app.notation.hand_split.SECONDS_PER_QUARTER (120 BPM) -- the
# pipeline's pre-beat-tracking fixed-tempo default. Used as the last-resort
# fallback when neither madmom nor librosa can produce any usable tempo
# estimate at all (e.g. truly silent or unreadable audio).
DEFAULT_SECONDS_PER_QUARTER = 0.5

# Same sane BPM clamp app.chords.detect uses for its librosa-based tempo
# estimate -- beat tracking on noisy/atypical audio occasionally returns
# implausible outliers (near-zero, or half/double-tempo errors).
MIN_TEMPO_BPM = 60.0
MAX_TEMPO_BPM = 200.0

# madmom's DBN beat tracker frame rate (frames/second of its activation
# function). 100 fps is madmom's own documented default/recommended value.
_MADMOM_FPS = 100

# RMS floor (on librosa's [-1, 1]-normalized samples) below which a clip is
# treated as near-silent/noise-floor-only rather than carrying real signal --
# e.g. a Demucs drums stem separated from a song with no percussion, which
# can still contain faint bleed-through of other instruments rather than
# true digital silence. Picked to sit well below any audibly-present source
# (a plain -20 dBFS tone has RMS ~0.07) while still comfortably above
# separation-artifact noise floors (~0.0005 RMS in practice).
_MIN_AUDIBLE_RMS = 0.01


class BeatMap:
    """Piecewise-linear mapping from audio seconds to quarterLength (beats),
    built from a sequence of detected beat timestamps where each beat = one
    quarter note.

    beat_times[i] is defined to be quarterLength position i (0-indexed):
    the first detected beat is quarterLength 0, the second is 1, and so on.
    Between two consecutive beats, position is linearly interpolated from
    the elapsed fraction of that inter-beat interval. Outside the detected
    range, position is extrapolated linearly using the first (or last)
    interval's local tempo -- i.e. we keep counting quarters at whatever
    tempo was in force at the nearest edge of the detected range.
    """

    def __init__(self, beat_times: list[float]):
        """beat_times: ascending timestamps in seconds, len >= 2."""
        beat_times = [float(t) for t in beat_times]
        if len(beat_times) < 2:
            raise ValueError("BeatMap requires at least 2 beat_times")
        for earlier, later in zip(beat_times, beat_times[1:]):
            if later <= earlier:
                raise ValueError("beat_times must be strictly ascending")
        self._beat_times = beat_times
        self._seconds_per_quarter = None  # only set by `constant`

    def to_quarter_length(self, seconds: float) -> float:
        """Convert an audio timestamp to a quarterLength position."""
        if self._seconds_per_quarter is not None:
            # Bypasses the piecewise machinery entirely so this is
            # byte-for-byte identical to the old `seconds / SECONDS_PER_QUARTER`
            # math -- see `constant`.
            return seconds / self._seconds_per_quarter

        times = self._beat_times
        last_index = len(times) - 1

        if seconds <= times[0]:
            interval = times[1] - times[0]
            return (seconds - times[0]) / interval
        if seconds >= times[-1]:
            interval = times[-1] - times[-2]
            return last_index + (seconds - times[-1]) / interval

        index = bisect.bisect_right(times, seconds) - 1
        interval = times[index + 1] - times[index]
        return index + (seconds - times[index]) / interval

    @classmethod
    def constant(cls, seconds_per_quarter: float) -> "BeatMap":
        """Degenerate fixed-tempo case for callers with no audio to detect
        from (e.g. existing tests, or a fallback). Must satisfy
        to_quarter_length(s) == s / seconds_per_quarter EXACTLY, so this
        stores seconds_per_quarter and answers with the literal expression
        `seconds / seconds_per_quarter` rather than routing through the
        piecewise beat_times math (which, while mathematically equivalent,
        is not guaranteed to be bit-identical after floating point
        rounding). That keeps this a byte-for-byte drop-in replacement for
        the pipeline's old fixed-tempo conversion, so existing
        golden-output tests elsewhere in the repo don't shift.
        """
        instance = cls.__new__(cls)
        instance._beat_times = None
        instance._seconds_per_quarter = seconds_per_quarter
        return instance

    def bpm_at(self, seconds: float) -> float:
        """Local tempo in BPM around the given timestamp.

        Approach: BPM = 60 / (local inter-beat interval in seconds), i.e.
        the same interval `to_quarter_length` is currently interpolating
        or extrapolating through -- a piecewise-*constant* tempo curve
        that underlies the piecewise-*linear* position map. This is
        best-effort/approximate by nature (real tempo can also curve
        within a single detected inter-beat interval), intended for
        eventually annotating tempo-change markings in exported notation,
        not for sample-accurate resynthesis.
        """
        if self._seconds_per_quarter is not None:
            return 60.0 / self._seconds_per_quarter

        times = self._beat_times
        if seconds <= times[0]:
            interval = times[1] - times[0]
        elif seconds >= times[-1]:
            interval = times[-1] - times[-2]
        else:
            index = bisect.bisect_right(times, seconds) - 1
            interval = times[index + 1] - times[index]
        return 60.0 / interval


# ---------------------------------------------------------------------------
# madmom / numpy 2.x compatibility shim
# ---------------------------------------------------------------------------
#
# madmom 0.16.1 (the latest release on PyPI as of this writing; there is no
# newer release and no actively-maintained numpy-2-compatible fork published
# there either) still uses numpy's pre-1.20 deprecated scalar aliases
# (np.float, np.int, np.object, np.complex, np.str, ...) both at import time
# (e.g. dtype tuples built at module scope) and at call time deep inside the
# actual beat-tracking code path (e.g. app.audio.signal's dtype coercion,
# the HMM in app.features.beats_hmm, tempo histogram code) -- numpy 2.0
# removed those aliases outright, raising AttributeError. Downgrading numpy
# is not an option here: librosa, basic-pitch, demucs, torch and
# piano_transcription_inference in this same venv all depend on numpy 2.x.
#
# The fix is a narrowly-scoped monkeypatch: temporarily restore just the
# handful of aliases madmom actually touches directly on the numpy module,
# run madmom's import and/or processing call, then put numpy back exactly
# as it was -- so no other code in the process ever observes the patched
# attributes. This is intentionally contained entirely within this module
# (not applied globally at process startup) specifically so it can't affect
# any other package's behavior.
#
# Caveat: because this patches the *global* numpy module object (there's no
# other way to shim attribute access on an already-imported C-backed
# module), it is not safe against another thread doing `np.float`-style
# access on a *different* deprecated alias at the exact same instant this
# is active. Nothing else in this codebase does that, and a module-level
# lock below at least serializes concurrent calls into this module so two
# overlapping detect_beat_map() calls can't race each other's patch/restore.
_NUMPY_LEGACY_ALIASES = {
    "float": float,
    "int": int,
    "object": object,
    "complex": complex,
    "str": str,
}
# Deliberately excludes "bool": numpy 2.0 re-added `np.bool` as a real
# scalar type (not removed like the others), so it's already present and
# must NOT be overwritten with the builtin -- madmom's `dtype=np.bool`
# usages work fine against numpy's own np.bool.

_madmom_import_lock = threading.Lock()


@contextmanager
def _numpy_legacy_aliases():
    sentinel = object()
    previous = {name: getattr(np, name, sentinel) for name in _NUMPY_LEGACY_ALIASES}
    for name, value in _NUMPY_LEGACY_ALIASES.items():
        if previous[name] is sentinel:
            setattr(np, name, value)
    try:
        yield
    finally:
        for name, prev_value in previous.items():
            if prev_value is sentinel:
                delattr(np, name)
            # else: attribute already existed before we entered (e.g. some
            # other, non-madmom-related code set it) -- leave it alone.


def _run_madmom_beat_tracking(audio_path: str) -> list[float]:
    with _madmom_import_lock, _numpy_legacy_aliases():
        from madmom.features.beats import DBNBeatTrackingProcessor, RNNBeatProcessor

        activations = RNNBeatProcessor()(audio_path)
        beats = DBNBeatTrackingProcessor(fps=_MADMOM_FPS)(activations)
    return [float(b) for b in beats]


def _librosa_fallback_beat_map(audio_path: str) -> BeatMap:
    """madmom couldn't produce >=2 usable beats (e.g. audio too short for
    its analysis window, or near-silent so its activation function never
    fires). Fall back to a coarser global tempo estimate from librosa's
    default beat tracker -- the same approach already used by
    app.chords.detect.detect_key_and_tempo -- clamped to a musically sane
    BPM range. If even that yields nothing usable (e.g. truly silent or
    unreadable audio, where librosa reports 0 BPM), fall back further to a
    fixed 120 BPM constant matching the pipeline's original, pre-beat-
    tracking default (app.notation.hand_split.SECONDS_PER_QUARTER)."""
    bpm = 0.0
    try:
        y, sr = librosa.load(audio_path, sr=None, mono=True)
        if y.size > 0:
            tempo, _beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            tempo_arr = np.atleast_1d(tempo)
            if tempo_arr.size:
                bpm = float(tempo_arr[0])
    except Exception:
        bpm = 0.0

    if bpm <= 0:
        return BeatMap.constant(DEFAULT_SECONDS_PER_QUARTER)
    bpm = min(max(bpm, MIN_TEMPO_BPM), MAX_TEMPO_BPM)
    return BeatMap.constant(60.0 / bpm)


def has_audible_signal(audio_path: str) -> bool:
    """Cheap gate for whether audio_path carries enough real signal to
    trust for beat detection, vs. near-silent/noise-floor-only content
    (e.g. a Demucs drums stem for a song with no percussion). Deliberately
    a plain RMS check rather than running madmom -- fast enough to call
    speculatively even on a stem we may end up not using."""
    try:
        y, _sr = librosa.load(audio_path, sr=None, mono=True)
    except Exception:
        return False
    if y.size == 0:
        return False
    return bool(np.sqrt(np.mean(np.square(y))) >= _MIN_AUDIBLE_RMS)


def detect_beat_map(audio_path: str) -> BeatMap:
    """Detect a real BeatMap from an audio file using madmom's neural beat
    tracker. If madmom can't produce at least 2 usable beat timestamps for
    a given clip (e.g. very short or silent audio), falls back to a
    librosa-based global tempo estimate, and if even that fails, to a
    fixed 120 BPM constant -- see `_librosa_fallback_beat_map`. Any
    unexpected error from madmom itself is treated the same way (logged by
    virtue of the exception type being swallowed here) rather than
    propagated, since a degraded tempo estimate is always preferable to
    failing the whole transcription pipeline.
    """
    try:
        beat_times = _run_madmom_beat_tracking(audio_path)
    except Exception:
        beat_times = []

    if len(beat_times) >= 2:
        return BeatMap(beat_times)
    return _librosa_fallback_beat_map(audio_path)
