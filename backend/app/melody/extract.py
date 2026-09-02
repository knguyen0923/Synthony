from app.notation.types import NoteEvent


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
