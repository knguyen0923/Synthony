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


_MIDDLE_C_MIDI = 60


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

    register_split = {
        "below_middle_c": sum(1 for p in pitches if p < _MIDDLE_C_MIDI),
        "at_or_above_middle_c": sum(1 for p in pitches if p >= _MIDDLE_C_MIDI),
    }

    return {
        "note_count": note_like_count,
        "event_count": len(notes),  # chords count as 1 event, N notes
        "pitch_range": pitch_range,
        "duration_histogram": duration_buckets,
        "voice_count": voice_info,
        "duration_quarter_length": float(part.highestTime),
        "register_split": register_split,
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


# Gross-failure thresholds for score_plausibility(). Only _HAND_BALANCE_MIN_FRACTION
# has a real calibration point: Big Rock's historical hand-split defect measured
# LH at 29/(1169+29) = 2.4% of total notes, comfortably below this threshold. The
# rest are reasonable-guess heuristics, not empirically validated against a labeled
# corpus -- this is a coarse proxy for catching gross failures, not a precision
# instrument. Tune freely if real runs show false positives/negatives.
_HAND_BALANCE_MIN_FRACTION = 0.10
_REGISTER_OVERLAP_MAX_FRACTION = 0.30
_SHORT_NOTE_MAX_FRACTION = 0.40
_MAX_PLAUSIBLE_SIMULTANEOUS_VOICES = 6
_MIN_NOTES_PER_QUARTER_LENGTH = 0.05
_MAX_NOTES_PER_QUARTER_LENGTH = 4.0

_SHORT_NOTE_BUCKET = "<16th (<0.25ql)"


def score_plausibility(parts: Dict) -> List[Dict]:
    """Heuristic pitch/rhythm plausibility scorer: flags gross failures in
    a tier's RH/LH output without a human needing to listen first. Takes
    the same {part_name: analyze_part()-dict} mapping analyze_musicxml()
    already returns for one tier. Returns a list of flagged-issue dicts
    (empty if nothing looks wrong) -- report-only, no aggregate score."""
    issues: List[Dict] = []
    rh = parts.get("Right Hand")
    lh = parts.get("Left Hand")

    if rh and lh:
        total_notes = rh["note_count"] + lh["note_count"]
        if total_notes > 0:
            rh_fraction = rh["note_count"] / total_notes
            lh_fraction = lh["note_count"] / total_notes
            if rh_fraction < _HAND_BALANCE_MIN_FRACTION:
                issues.append({
                    "check": "hand_balance", "part": "Right Hand",
                    "detail": f"Right Hand has only {rh_fraction:.1%} of total RH+LH notes",
                })
            if lh_fraction < _HAND_BALANCE_MIN_FRACTION:
                issues.append({
                    "check": "hand_balance", "part": "Left Hand",
                    "detail": f"Left Hand has only {lh_fraction:.1%} of total RH+LH notes",
                })

    for part_name, part in parts.items():
        note_count = part["note_count"]
        if note_count == 0:
            continue

        register_split = part.get("register_split")
        if register_split:
            if part_name == "Right Hand":
                fraction = register_split["below_middle_c"] / note_count
                if fraction > _REGISTER_OVERLAP_MAX_FRACTION:
                    issues.append({
                        "check": "register_overlap", "part": part_name,
                        "detail": f"{fraction:.1%} of Right Hand notes fall below middle C",
                    })
            elif part_name == "Left Hand":
                fraction = register_split["at_or_above_middle_c"] / note_count
                if fraction > _REGISTER_OVERLAP_MAX_FRACTION:
                    issues.append({
                        "check": "register_overlap", "part": part_name,
                        "detail": f"{fraction:.1%} of Left Hand notes fall at or above middle C",
                    })

        short_note_count = part.get("duration_histogram", {}).get(_SHORT_NOTE_BUCKET, 0)
        short_fraction = short_note_count / note_count
        if short_fraction > _SHORT_NOTE_MAX_FRACTION:
            issues.append({
                "check": "note_duration_sanity", "part": part_name,
                "detail": f"{short_fraction:.1%} of {part_name} notes are shorter than a 16th note",
            })

        peak_voices = part.get("voice_count", {}).get("peak_simultaneous_voices", 0)
        if peak_voices > _MAX_PLAUSIBLE_SIMULTANEOUS_VOICES:
            issues.append({
                "check": "voice_count_sanity", "part": part_name,
                "detail": f"{part_name} peaks at {peak_voices} simultaneous notes (>{_MAX_PLAUSIBLE_SIMULTANEOUS_VOICES})",
            })

        duration_ql = part.get("duration_quarter_length", 0)
        if duration_ql > 0:
            density = note_count / duration_ql
            if density < _MIN_NOTES_PER_QUARTER_LENGTH:
                issues.append({
                    "check": "note_density_sanity", "part": part_name,
                    "detail": f"{part_name} averages only {density:.3f} notes per quarter-length (near-silent)",
                })
            elif density > _MAX_NOTES_PER_QUARTER_LENGTH:
                issues.append({
                    "check": "note_density_sanity", "part": part_name,
                    "detail": f"{part_name} averages {density:.1f} notes per quarter-length (implausibly dense)",
                })

    return issues


def export_midi(musicxml_path: Path, dest_midi_path: Path) -> Path:
    score = m21.converter.parse(str(musicxml_path))
    dest_midi_path.parent.mkdir(parents=True, exist_ok=True)
    score.write("midi", fp=str(dest_midi_path))
    return dest_midi_path


def save_json(data: Dict, dest_path: Path) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(json.dumps(data, indent=2, sort_keys=True))
    return dest_path
