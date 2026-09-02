from music21 import stream

from app.notation.hand_split import SECONDS_PER_QUARTER, notes_to_part
from app.notation.types import NoteEvent
from app.transcription.audio_to_midi import transcribe_audio_to_notes


def reduce_to_monophonic(notes: list[NoteEvent]) -> list[NoteEvent]:
    """Collapse polyphonic note detections to a single melody line: when
    two notes overlap in time, keep only the higher-pitched one (the
    sung/played melody is assumed to be the top voice), discarding the
    other entirely."""
    ordered = sorted(notes, key=lambda n: n.start)
    melody: list[NoteEvent] = []
    for candidate in ordered:
        if melody and candidate.start < melody[-1].end:
            if candidate.pitch > melody[-1].pitch:
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


def quantize_melody(notes: list[NoteEvent], grid: float) -> list[NoteEvent]:
    """Snap note onsets to `grid` (in quarterLength units — 1.0 = quarter
    note, 0.5 = eighth, etc.), drop duplicate re-attacks that land in the
    same grid slot, and legato each kept note into the next one's onset so
    the melody sustains instead of stopping short. The last note is
    floored to at least one grid step, so it isn't left too short to
    register when nothing follows it to legato into."""
    grid_seconds = grid * SECONDS_PER_QUARTER
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


def melody_part_for_tier(notes: list[NoteEvent], grid: float) -> stream.Part:
    """Quantize a reduced melody note list to `grid` and build the
    resulting RH Part — the per-tier entry point arrange_pipeline uses."""
    return notes_to_part(quantize_melody(notes, grid), part_id="RH")
