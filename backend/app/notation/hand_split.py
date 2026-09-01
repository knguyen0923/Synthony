from music21 import stream, note, clef

from app.notation.types import NoteEvent

# Fixed-tempo assumption for v1 — tempo detection is out of scope.
SECONDS_PER_QUARTER = 0.5  # 120 BPM


def _seconds_to_quarter_length(seconds: float) -> float:
    return seconds / SECONDS_PER_QUARTER


def _to_music21_note(event: NoteEvent) -> note.Note:
    m21_note = note.Note()
    m21_note.pitch.midi = event.pitch
    duration = _seconds_to_quarter_length(event.end - event.start)
    m21_note.duration.quarterLength = max(duration, 0.25)
    return m21_note


def notes_to_grand_staff(notes: list[NoteEvent]) -> stream.Score:
    """Group notes by onset; the highest-pitched note at each onset is the
    melody and always goes to the right hand, regardless of its absolute
    pitch. Every other simultaneous note goes to the left hand."""
    rh = stream.Part(id="RH")
    rh.append(clef.TrebleClef())
    lh = stream.Part(id="LH")
    lh.append(clef.BassClef())

    by_onset: dict[float, list[NoteEvent]] = {}
    for event in notes:
        by_onset.setdefault(round(event.start, 3), []).append(event)

    for onset in sorted(by_onset):
        group = sorted(by_onset[onset], key=lambda e: e.pitch)
        melody_event = group[-1]
        accompaniment = group[:-1]

        offset = _seconds_to_quarter_length(melody_event.start)
        rh.insert(offset, _to_music21_note(melody_event))
        for event in accompaniment:
            lh.insert(_seconds_to_quarter_length(event.start), _to_music21_note(event))

    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)
    return score


def get_hand_parts(score: stream.Score) -> tuple[stream.Part, stream.Part]:
    rh = next(p for p in score.parts if p.id == "RH")
    lh = next(p for p in score.parts if p.id == "LH")
    return rh, lh
