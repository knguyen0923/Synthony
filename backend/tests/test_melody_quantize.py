from app.melody.extract import quantize_melody
from app.notation.hand_split import SECONDS_PER_QUARTER
from app.notation.types import NoteEvent

QUARTER_GRID = 1.0  # in quarterLength units, matching quantize_melody's grid parameter


def test_quantize_melody_dedups_notes_within_the_same_grid_slot():
    # Both onsets fall inside the same quarter-note slot starting at t=0
    # (slot width = 1 quarterLength = SECONDS_PER_QUARTER seconds).
    notes = [
        NoteEvent(start=0.0, end=0.1, pitch=60),
        NoteEvent(start=0.1, end=0.2, pitch=62),
    ]
    result = quantize_melody(notes, QUARTER_GRID)
    assert len(result) == 1
    assert result[0].pitch == 60


def test_quantize_melody_extends_notes_to_meet_the_next_onset():
    grid_seconds = QUARTER_GRID * SECONDS_PER_QUARTER
    notes = [
        NoteEvent(start=0.0, end=0.05, pitch=60),  # much shorter than the gap to the next note
        NoteEvent(start=2 * grid_seconds, end=2 * grid_seconds + 0.05, pitch=64),
    ]
    result = quantize_melody(notes, QUARTER_GRID)
    assert result[0].end == 2 * grid_seconds  # legato — sustains until the next note starts
    assert result[1].pitch == 64


def test_quantize_melody_floors_the_last_note_to_one_grid_step():
    grid_seconds = QUARTER_GRID * SECONDS_PER_QUARTER
    notes = [NoteEvent(start=0.0, end=0.02, pitch=60)]  # far shorter than a grid step, nothing after it
    result = quantize_melody(notes, QUARTER_GRID)
    assert result[0].end - result[0].start >= grid_seconds


def test_quantize_melody_respects_a_non_default_tempo():
    # At 1.0 seconds-per-quarter (60 BPM), a quarter-note grid slot is
    # 1.0s wide instead of the default 0.5s — these two onsets land in
    # different slots at the default tempo (round(0.3/0.5) = 1) but the
    # same slot at this one (round(0.3/1.0) = 0).
    notes = [
        NoteEvent(start=0.0, end=0.1, pitch=60),
        NoteEvent(start=0.3, end=0.4, pitch=62),
    ]
    result = quantize_melody(notes, QUARTER_GRID, seconds_per_quarter=1.0)
    assert len(result) == 1
