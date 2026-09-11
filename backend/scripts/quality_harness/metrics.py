"""Objective, comparable metrics extracted from a piano-arrangement
MusicXML file via music21. Designed to be diffed run-over-run (e.g.
baseline vs. after a sibling agent's change lands) without needing to
listen to anything, plus a MIDI export for the listening pass a human
still needs to do.

All functions operate on a single MusicXML file (one difficulty tier)
and return a plain-JSON-serializable dict.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import music21 as m21

# Duration-bucket boundaries in quarterLength, used instead of relying on
# music21's duration.type (which reports "complex"/"zero" for anything
# that doesn't land on a clean notated value — common on real-audio
# transcription output with onset jitter).
_DURATION_BUCKETS = [
    ("<16th (<0.25ql)", 0.0, 0.25),
    ("16th (0.25-0.375ql)", 0.25, 0.375),
    ("dotted-16th/8th (0.375-0.625ql)", 0.375, 0.625),
    ("dotted-8th/quarter (0.625-0.875ql)", 0.625, 0.875),
    ("quarter (0.875-1.25ql)", 0.875, 1.25),
    ("dotted-quarter (1.25-1.75ql)", 1.25, 1.75),
    ("half (1.75-2.5ql)", 1.75, 2.5),
    ("dotted-half/whole (2.5-4.5ql)", 2.5, 4.5),
    (">whole (>=4.5ql)", 4.5, float("inf")),
]


def _bucket_for(quarter_length: float) -> str:
    for label, lo, hi in _DURATION_BUCKETS:
        if lo <= quarter_length < hi:
            return label
    return _DURATION_BUCKETS[-1][0]


def _voice_count_series(notes: List, step: float = 0.25) -> Dict:
    """Sweep-line simultaneous-voice count, sampled every `step`
    quarterLength across the part's span. Returns peak, mean, and a
    histogram of how many samples had each voice count (0..N)."""
    if not notes:
        return {"peak_simultaneous_voices": 0, "mean_simultaneous_voices": 0.0, "histogram": {}}

    spans = sorted((float(n.offset), float(n.offset) + float(n.duration.quarterLength)) for n in notes)
    end = max(hi for _, hi in spans)
    t = 0.0
    samples = []
    # Sample at note onsets too (not just the fixed grid) so brief,
    # off-grid dense clusters aren't averaged away.
    onset_points = sorted({round(lo, 6) for lo, _ in spans})
    grid_points = []
    while t <= end:
        grid_points.append(round(t, 6))
        t += step
    all_points = sorted(set(onset_points) | set(grid_points))

    for point in all_points:
        count = sum(1 for lo, hi in spans if lo <= point < hi)
        samples.append(count)

    histogram: Dict[str, int] = {}
    for c in samples:
        histogram[str(c)] = histogram.get(str(c), 0) + 1

    return {
        "peak_simultaneous_voices": max(samples),
        "mean_simultaneous_voices": round(sum(samples) / len(samples), 3),
        "histogram": histogram,
    }


def analyze_part(part: m21.stream.Part) -> Dict:
    notes = list(part.flatten().notes)
    # Expand chords into their constituent pitches for pitch-range /
    # duration stats (a chord counts as N simultaneous notes of the same
    # duration), but keep the original Note/Chord objects for the
    # voice-count sweep (a Chord object's own span already represents
    # all its pitches sounding at once).
    pitches: List[int] = []
    duration_buckets: Dict[str, int] = {}
    note_like_count = 0

    for el in notes:
        if isinstance(el, m21.chord.Chord):
            ps = el.pitches
        elif isinstance(el, m21.note.Note):
            ps = [el.pitch]
        else:
            continue
        note_like_count += len(ps)
        for p in ps:
            pitches.append(p.midi)
        bucket = _bucket_for(float(el.duration.quarterLength))
        duration_buckets[bucket] = duration_buckets.get(bucket, 0) + len(ps)

    voice_info = _voice_count_series(notes)

    pitch_range = None
    if pitches:
        pitch_range = {
            "min_midi": min(pitches),
            "max_midi": max(pitches),
            "min_name": m21.pitch.Pitch(min(pitches)).nameWithOctave,
            "max_name": m21.pitch.Pitch(max(pitches)).nameWithOctave,
            "span_semitones": max(pitches) - min(pitches),
        }

    return {
        "note_count": note_like_count,
        "event_count": len(notes),  # chords count as 1 event, N notes
        "pitch_range": pitch_range,
        "duration_histogram": duration_buckets,
        "voice_count": voice_info,
        "duration_quarter_length": float(part.highestTime),
    }


def analyze_musicxml(path: Path) -> Dict:
    """Parse one MusicXML file and return per-part metrics plus overall
    score-level info (title, total length)."""
    score = m21.converter.parse(str(path))
    parts = list(score.parts) if score.parts else [score]

    result = {
        "source_file": str(path),
        "score_title": _score_title(score),
        "duration_quarter_length": float(score.highestTime),
        "parts": {},
    }
    for idx, part in enumerate(parts):
        part_name = part.partName or f"part_{idx}"
        result["parts"][part_name] = analyze_part(part)
    return result


def _score_title(score: m21.stream.Score) -> str:
    if score.metadata and score.metadata.title:
        return score.metadata.title
    return "Untitled"


def export_midi(musicxml_path: Path, dest_midi_path: Path) -> Path:
    score = m21.converter.parse(str(musicxml_path))
    dest_midi_path.parent.mkdir(parents=True, exist_ok=True)
    score.write("midi", fp=str(dest_midi_path))
    return dest_midi_path


def save_json(data: Dict, dest_path: Path) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(data, indent=2, sort_keys=True))
    return dest_path
