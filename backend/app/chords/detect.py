import librosa
import numpy as np

from app.chords.key import detect_key

MIN_TEMPO_BPM = 60.0
MAX_TEMPO_BPM = 200.0
DEFAULT_SECONDS_PER_QUARTER = 0.5  # 120 BPM fallback if beat-tracking yields nothing usable


def _tempo_to_seconds_per_quarter(tempo) -> float:
    """Convert a detected tempo (BPM, possibly a numpy scalar/array, or
    falsy) to seconds-per-quarter-note, clamped to a musically sane range
    — beat tracking on noisy or atypical audio occasionally returns
    implausible outliers (near-zero, or half/double-tempo errors)."""
    bpm = float(np.atleast_1d(tempo)[0]) if tempo else 0.0
    if bpm <= 0:
        return DEFAULT_SECONDS_PER_QUARTER
    bpm = min(max(bpm, MIN_TEMPO_BPM), MAX_TEMPO_BPM)
    return 60.0 / bpm


def detect_key_and_tempo(audio_path: str) -> tuple[tuple[int, str], float]:
    """Detect the song's key (tonic pitch class, mode) and tempo (as
    seconds-per-quarter-note) from an audio file. Chroma-based key
    detection and beat-tracking only — no chord-per-bar matching; LH now
    comes from a real transcription (app.lh.extract) rather than chord
    symbols, so this only needs to supply the key signature and the
    tempo used to convert note timings."""
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    key = detect_key(chroma)
    tempo, _beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    seconds_per_quarter = _tempo_to_seconds_per_quarter(tempo)
    return key, seconds_per_quarter
