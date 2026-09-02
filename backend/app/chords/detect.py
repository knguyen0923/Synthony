import librosa
import numpy as np

from app.arrangement.types import ChordSymbol
from app.chords.match import match_chord

BEATS_PER_BAR = 4  # assumes 4/4 time — a fixed-grid simplification, same
                    # spirit as the rest of this codebase's fixed-tempo
                    # assumptions


def detect_chords(audio_path: str) -> list[ChordSymbol]:
    """Detect a chord-per-bar sequence from an audio file: chroma
    features aggregated over 4-beat bars, matched against chord
    templates, with consecutive identical chords merged into one
    ChordSymbol."""
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    duration = len(y) / sr

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    _tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
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
        root, quality = match_chord(bar_chroma)
        raw_chords.append(ChordSymbol(start=float(start), duration=float(end - start), root=root, quality=quality))

    return _merge_consecutive(raw_chords)


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
