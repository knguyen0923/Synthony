from typing import Optional

from music21 import stream, note, clef, layout, metadata

from app.notation.types import NoteEvent

# Fixed-tempo assumption for v1 — tempo detection is out of scope.
SECONDS_PER_QUARTER = 0.5  # 120 BPM

# Audio timing must always be expressible in MusicXML. Round to nearest 32nd note
# for guaranteed notation compatibility; this is imperceptible rhythmic resolution.
NOTATION_GRID = 0.125  # nearest 32nd note (quarter note = 1.0, eighth = 0.5, etc.)

# The melody-aware hand split assigns notes by "highest simultaneous pitch",
# never by absolute register (per spec) — so a melody line can legitimately
# dip into the bass register (or an accompaniment line rise into the treble
# register), which would otherwise render as a wall of ledger lines. Real
# engraved piano music handles this with a temporary clef change for the
# sustained passage, not by reassigning notes to the other hand — this only
# changes which clef a hand's own notes are drawn with.
RH_LOW_REGISTER_THRESHOLD = 55  # G3 — sustained RH notes at/below this get a temporary bass clef
LH_HIGH_REGISTER_THRESHOLD = 67  # G4 — sustained LH notes at/above this get a temporary treble clef
MIN_CLEF_CHANGE_RUN = 4  # consecutive notes required before switching, to avoid flicker on passing tones


def _seconds_to_quarter_length(seconds: float) -> float:
    return seconds / SECONDS_PER_QUARTER


def _round_to_grid(value: float, grid: float) -> float:
    """Round a value to the nearest grid step."""
    return round(value / grid) * grid


def _to_music21_note(event: NoteEvent, seconds_per_quarter: float = SECONDS_PER_QUARTER) -> note.Note:
    m21_note = note.Note()
    m21_note.pitch.midi = event.pitch
    duration = (event.end - event.start) / seconds_per_quarter
    duration = max(duration, NOTATION_GRID)
    m21_note.duration.quarterLength = _round_to_grid(duration, NOTATION_GRID)
    return m21_note


def _apply_dynamic_clef_changes(part: stream.Part, home_clef_cls, away_clef_cls, is_away) -> None:
    """Insert temporary clef changes wherever `part` has a sustained run of
    notes that belongs more naturally in the other clef, switching back once
    the run ends. Replaces whatever static clef the part already had."""
    for existing in list(part.getElementsByClass(clef.Clef)):
        part.remove(existing)

    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    if not notes:
        part.insert(0, home_clef_cls())
        return

    away_flags = [is_away(n) for n in notes]
    # Smooth out short excursions (below MIN_CLEF_CHANGE_RUN) so a single
    # passing tone doesn't trigger a clef change.
    i = 0
    while i < len(away_flags):
        j = i
        while j < len(away_flags) and away_flags[j] == away_flags[i]:
            j += 1
        if away_flags[i] and (j - i) < MIN_CLEF_CHANGE_RUN:
            for k in range(i, j):
                away_flags[k] = False
        i = j

    first_offset = notes[0].offset
    if first_offset > 0 or not away_flags[0]:
        part.insert(0, home_clef_cls())
        current_away = False
    else:
        part.insert(0, away_clef_cls())
        current_away = True

    for note_obj, away in zip(notes, away_flags):
        if away and not current_away:
            part.insert(note_obj.offset, away_clef_cls())
            current_away = True
        elif not away and current_away:
            part.insert(note_obj.offset, home_clef_cls())
            current_away = False


def build_grand_staff_score(
    rh: stream.Part, lh: stream.Part, title: Optional[str] = None
) -> stream.Score:
    """Assemble RH/LH parts into a Score with a piano brace connecting them,
    so exported MusicXML renders as a single connected grand staff rather
    than two independent staves. Every score-construction site (raw
    grand-staff assembly, and each difficulty tier that builds a fresh
    Score from its own RH/LH parts) must go through this helper — Hard's
    deepcopy passthrough is the only exception, since it inherits the
    brace, part names, and title from its input score automatically.

    Also names the parts ("Right Hand"/"Left Hand") and, when given, sets
    the Score's title — without these, music21 exports an empty
    <part-name> (rendered by viewers as the internal id, an opaque hex
    string) and a placeholder "Music21 Fragment" title."""
    # Kept internally (non-empty <part-name>, needed to avoid viewers
    # falling back to the opaque internal part id) but not printed — a
    # single piano's two staves don't need a label in real engraved scores,
    # there's no ambiguity about which hand plays which staff.
    rh.partName = "Right Hand"
    rh.style.printPartName = False
    lh.partName = "Left Hand"
    lh.style.printPartName = False

    _apply_dynamic_clef_changes(
        rh, clef.TrebleClef, clef.BassClef,
        is_away=lambda n: n.pitch.midi <= RH_LOW_REGISTER_THRESHOLD,
    )
    _apply_dynamic_clef_changes(
        lh, clef.BassClef, clef.TrebleClef,
        is_away=lambda n: n.pitch.midi >= LH_HIGH_REGISTER_THRESHOLD,
    )

    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)
    score.insert(0, layout.StaffGroup([rh, lh], name="Piano", abbreviation="Pno.", symbol="brace"))
    if title:
        score.metadata = metadata.Metadata()
        score.metadata.title = title
    return score


def notes_to_grand_staff(notes: list[NoteEvent], title: Optional[str] = None) -> stream.Score:
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

    return build_grand_staff_score(rh, lh, title=title)


def notes_to_part(notes: list[NoteEvent], part_id: str = "RH", seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """Build a single-line Part from a flat list of NoteEvents, e.g. an
    already-reduced monophonic melody line. Unlike notes_to_grand_staff,
    this does no RH/LH splitting — every note goes into one Part, in
    onset order."""
    part = stream.Part(id=part_id)
    part.append(clef.TrebleClef())
    for event in sorted(notes, key=lambda e: e.start):
        offset = _round_to_grid(event.start / seconds_per_quarter, NOTATION_GRID)
        part.insert(offset, _to_music21_note(event, seconds_per_quarter))
    return part


def get_title(score: stream.Score) -> Optional[str]:
    """Read back the title set by build_grand_staff_score(), so a difficulty
    tier that builds a fresh Score from its own RH/LH parts can carry the
    title forward from its input score."""
    return score.metadata.title if score.metadata else None


def get_hand_parts(score: stream.Score) -> tuple[stream.Part, stream.Part]:
    rh = next(p for p in score.parts if p.id == "RH")
    lh = next(p for p in score.parts if p.id == "LH")
    return rh, lh
