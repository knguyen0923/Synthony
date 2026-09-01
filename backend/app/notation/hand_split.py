from music21 import stream, note, clef, layout

from app.notation.types import NoteEvent

# Fixed-tempo assumption for v1 — tempo detection is out of scope.
SECONDS_PER_QUARTER = 0.5  # 120 BPM

# Audio timing must always be expressible in MusicXML. Round to nearest 32nd note
# for guaranteed notation compatibility; this is imperceptible rhythmic resolution.
NOTATION_GRID = 0.125  # nearest 32nd note (quarter note = 1.0, eighth = 0.5, etc.)


def _seconds_to_quarter_length(seconds: float) -> float:
    return seconds / SECONDS_PER_QUARTER


def _round_to_grid(value: float, grid: float) -> float:
    """Round a value to the nearest grid step."""
    return round(value / grid) * grid


def _to_music21_note(event: NoteEvent) -> note.Note:
    m21_note = note.Note()
    m21_note.pitch.midi = event.pitch
    duration = _seconds_to_quarter_length(event.end - event.start)
    # Apply minimum duration floor at grid resolution, then round to grid
    # to ensure all durations are MusicXML-expressible.
    duration = max(duration, NOTATION_GRID)
    m21_note.duration.quarterLength = _round_to_grid(duration, NOTATION_GRID)
    return m21_note


def build_grand_staff_score(rh: stream.Part, lh: stream.Part) -> stream.Score:
    """Assemble RH/LH parts into a Score with a piano brace connecting them,
    so exported MusicXML renders as a single connected grand staff rather
    than two independent staves. Every score-construction site (raw
    grand-staff assembly, and each difficulty tier that builds a fresh
    Score from its own RH/LH parts) must go through this helper — Hard's
    deepcopy passthrough is the only exception, since it inherits the
    brace from its input score automatically."""
    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)
    score.insert(0, layout.StaffGroup([rh, lh], name="Piano", abbreviation="Pno.", symbol="brace"))
    return score


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
        offset = _round_to_grid(offset, NOTATION_GRID)
        rh.insert(offset, _to_music21_note(melody_event))
        for event in accompaniment:
            acc_offset = _seconds_to_quarter_length(event.start)
            acc_offset = _round_to_grid(acc_offset, NOTATION_GRID)
            lh.insert(acc_offset, _to_music21_note(event))

    return build_grand_staff_score(rh, lh)


def get_hand_parts(score: stream.Score) -> tuple[stream.Part, stream.Part]:
    rh = next(p for p in score.parts if p.id == "RH")
    lh = next(p for p in score.parts if p.id == "LH")
    return rh, lh
