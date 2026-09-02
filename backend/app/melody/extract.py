from music21 import stream

from app.notation.hand_split import notes_to_part
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


def extract_melody_part(audio_path: str) -> stream.Part:
    """Run Basic Pitch on a (typically vocal-isolated) audio file and
    reduce its output to a single melody line as an RH Part."""
    notes = transcribe_audio_to_notes(audio_path)
    melody_notes = reduce_to_monophonic(notes)
    return notes_to_part(melody_notes, part_id="RH")
