from typing import Optional

from music21 import stream

from app.difficulty.range_shift import shift_into_range
from app.notation.hand_split import SECONDS_PER_QUARTER, notes_to_part
from app.notation.types import NoteEvent
from app.notation.voice_cap import cap_simultaneous_notes  # noqa: F401 (re-exported for existing importers)
from app.tempo.detect import BeatMap
from app.transcription.audio_to_midi import transcribe_audio_to_notes

HARD_MAX_VOICES = 4  # a plausible upper bound on notes one hand plays at once
HARD_LH_RANGE = (36, 55)  # C2-G3, same bass register as the previous Hard tier


def extract_lh_notes(audio_path: str, max_voices: int = HARD_MAX_VOICES) -> list[NoteEvent]:
    """Run Basic Pitch on harmony audio (bass+other mix) and cap to
    max_voices concurrently-sounding notes. Unlike RH, deliberately keeps
    polyphony — real LH accompaniment is chordal, not a single line."""
    notes = transcribe_audio_to_notes(audio_path)
    return cap_simultaneous_notes(notes, max_voices)


def build_lh_part(
    notes: list[NoteEvent], seconds_per_quarter: float = SECONDS_PER_QUARTER, beat_map: Optional[BeatMap] = None
) -> stream.Part:
    """Register-shift the capped transcription into HARD_LH_RANGE and
    build the LH 'Hard' Part — the full-detail base every difficulty tier
    derives from, same role as melody.extract.build_melody_part for RH.

    beat_map, when given, overrides seconds_per_quarter for note timing."""
    part = notes_to_part(notes, part_id="LH", seconds_per_quarter=seconds_per_quarter, beat_map=beat_map)
    return shift_into_range(part, *HARD_LH_RANGE)
