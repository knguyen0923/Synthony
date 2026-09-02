import librosa
import numpy as np

from app.arrangement.types import ChordSymbol
from app.chords.key import detect_key
from app.chords.match import match_chord

BEATS_PER_BAR = 4  # assumes 4/4 time — a fixed-grid simplification, same
                    # spirit as the rest of this codebase's fixed-tempo
                    # assumptions
MIN_CHORD_DURATION = 2.0  # seconds — a detected chord shorter than this is
                            # treated as a bar-detection/chroma-noise blip
                            # and absorbed into its neighbor, rather than
                            # letting the LH re-trigger on every one
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


def detect_chords(audio_path: str) -> tuple[list[ChordSymbol], float]:
    """Detect a chord-per-bar sequence from an audio file, along with the
    song's own detected tempo (as seconds-per-quarter-note) so callers can
    convert chord/melody timing using the song's real tempo instead of a
    fixed assumption. Chroma features aggregated over 4-beat bars,
    matched against chord templates, with consecutive identical chords
    merged and short blips absorbed into their neighbor."""
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration = len(y) / sr

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    key = detect_key(chroma)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    seconds_per_quarter = _tempo_to_seconds_per_quarter(tempo)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    bar_starts = list(beat_times[::BEATS_PER_BAR])
    if not bar_starts or bar_starts[0] > 0:
        bar_starts.insert(0, 0.0)
    bar_starts.append(duration)

    chroma_times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr)

    raw_chords: list[ChordSymbol] = []
    for start, end in zip(bar_starts[:-1], bar_starts[1:]):
        if end <= start:
            continue
        in_bar = (chroma_times >= start) & (chroma_times < end)
        if not np.any(in_bar):
            continue
        bar_chroma = chroma[:, in_bar].mean(axis=1)
        root, quality = match_chord(bar_chroma, key=key)
        raw_chords.append(ChordSymbol(start=float(start), duration=float(end - start), root=root, quality=quality))

    chords = _absorb_short_chords(_merge_consecutive(raw_chords))
    return chords, seconds_per_quarter


def _absorb_short_chords(chords: list[ChordSymbol], min_duration: float = MIN_CHORD_DURATION) -> list[ChordSymbol]:
    """Merge any chord shorter than min_duration into its neighbor —
    absorbed into the previous chord where one exists, otherwise into the
    next one — then re-merge so a newly-adjacent identical pair collapses
    into one."""
    if not chords:
        return []

    result = [chords[0]]
    for chord in chords[1:]:
        if chord.duration < min_duration:
            last = result[-1]
            result[-1] = ChordSymbol(
                start=last.start,
                duration=last.duration + chord.duration,
                root=last.root,
                quality=last.quality,
            )
        else:
            result.append(chord)

    if len(result) > 1 and result[0].duration < min_duration:
        leading, following = result[0], result[1]
        result[1] = ChordSymbol(
            start=leading.start,
            duration=leading.duration + following.duration,
            root=following.root,
            quality=following.quality,
        )
        result.pop(0)

    return _merge_consecutive(result)


def _merge_consecutive(chords: list[ChordSymbol]) -> list[ChordSymbol]:
    if not chords:
        return []

    merged = [chords[0]]
    for chord in chords[1:]:
        last = merged[-1]
        if chord.root == last.root and chord.quality == last.quality:
            merged[-1] = ChordSymbol(
                start=last.start,
                duration=last.duration + chord.duration,
                root=last.root,
                quality=last.quality,
            )
        else:
            merged.append(chord)
    return merged
