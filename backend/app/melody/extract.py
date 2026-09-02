from music21 import stream

from app.notation.hand_split import SECONDS_PER_QUARTER, notes_to_part
from app.notation.types import NoteEvent
from app.transcription.audio_to_midi import transcribe_audio_to_notes


def reduce_to_monophonic(notes: list[NoteEvent]) -> list[NoteEvent]:
    """Collapse polyphonic note detections to a single melody line: when
    two notes overlap in time, keep whichever has higher confidence
    (velocity), discarding the other entirely. Basic Pitch commonly
    detects an octave-doubled harmonic alongside the true sung note —
    that artifact is usually higher-pitched but lower-confidence than the
    real one, so picking by pitch alone was systematically biased toward
    the wrong octave."""
    ordered = sorted(notes, key=lambda n: n.start)
    melody: list[NoteEvent] = []
    for candidate in ordered:
        if melody and candidate.start < melody[-1].end:
            if candidate.velocity > melody[-1].velocity:
                melody[-1] = candidate
        else:
            melody.append(candidate)
    return melody


def extract_melody_notes(audio_path: str) -> list[NoteEvent]:
    """Run Basic Pitch on a (typically vocal-isolated) audio file and
    reduce its output to a single melody line, as a flat NoteEvent list.
    Callers quantize per difficulty tier (see quantize_melody) before
    building a Part."""
    notes = transcribe_audio_to_notes(audio_path)
    return reduce_to_monophonic(notes)


def quantize_melody(notes: list[NoteEvent], grid: float, seconds_per_quarter: float = SECONDS_PER_QUARTER) -> list[NoteEvent]:
    """Snap note onsets to `grid` (in quarterLength units — 1.0 = quarter
    note, 0.5 = eighth, etc.) at the given tempo, drop duplicate
    re-attacks that land in the same grid slot, and legato each kept note
    into the next one's onset so the melody sustains instead of stopping
    short. The last note is floored to at least one grid step, so it
    isn't left too short to register when nothing follows it to legato
    into."""
    grid_seconds = grid * seconds_per_quarter
    ordered = sorted(notes, key=lambda n: n.start)

    kept: list[NoteEvent] = []
    seen_slots: set[int] = set()
    for candidate in ordered:
        slot = round(candidate.start / grid_seconds)
        if slot in seen_slots:
            continue
        seen_slots.add(slot)
        kept.append(NoteEvent(start=slot * grid_seconds, end=candidate.end, pitch=candidate.pitch, velocity=candidate.velocity))

    for i in range(len(kept) - 1):
        if kept[i].end < kept[i + 1].start:
            kept[i] = NoteEvent(start=kept[i].start, end=kept[i + 1].start, pitch=kept[i].pitch, velocity=kept[i].velocity)

    if kept and kept[-1].end - kept[-1].start < grid_seconds:
        last = kept[-1]
        kept[-1] = NoteEvent(start=last.start, end=last.start + grid_seconds, pitch=last.pitch, velocity=last.velocity)

    return kept


# A fine, tier-independent grid used once to clean up the raw extracted
# melody (fixes fragmented, "barely pressing the keys" onsets via
# quantize_melody's legato extension) before any per-tier difficulty
# simplification is layered on top. Sixteenth notes preserve essentially
# all real melodic detail while still closing genuinely broken gaps.
CLEANUP_GRID = 0.25


def build_melody_part(notes: list[NoteEvent], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """Clean up a reduced melody note list (legato, de-fragmented) and
    build the resulting RH Part. This is the full-detail base every
    difficulty tier derives from."""
    return notes_to_part(quantize_melody(notes, CLEANUP_GRID, seconds_per_quarter), part_id="RH", seconds_per_quarter=seconds_per_quarter)
