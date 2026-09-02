from music21 import stream

from app.difficulty.range_shift import shift_into_range
from app.notation.hand_split import SECONDS_PER_QUARTER, notes_to_part
from app.notation.types import NoteEvent
from app.transcription.audio_to_midi import transcribe_audio_to_notes

HARD_MAX_VOICES = 4  # a plausible upper bound on notes one hand plays at once
HARD_LH_RANGE = (36, 55)  # C2-G3, same bass register as the previous Hard tier


def cap_simultaneous_notes(notes: list[NoteEvent], max_voices: int) -> list[NoteEvent]:
    """At every moment, keep at most max_voices concurrently-sounding
    notes — the highest-velocity ones — discarding the rest. Basic Pitch
    on a busy 'other' stem (piano/guitar/strings/synths — whatever Demucs
    didn't call vocals/drums/bass) can over-detect beyond what a hand can
    physically play; this caps to a plausible upper bound rather than
    trusting raw detection count, generalizing melody.extract's
    reduce_to_monophonic (confidence-over-raw-detection) from 1 voice to
    N. On a tie, the earlier-processed (already-held) note wins."""
    ordered = sorted(notes, key=lambda n: n.start)
    held: list[NoteEvent] = []
    kept: list[NoteEvent] = []
    for candidate in ordered:
        held = [n for n in held if n.end > candidate.start]
        if len(held) < max_voices:
            held.append(candidate)
            kept.append(candidate)
            continue
        weakest = min(held, key=lambda n: n.velocity)
        if candidate.velocity <= weakest.velocity:
            continue
        held.remove(weakest)
        kept.remove(weakest)
        held.append(candidate)
        kept.append(candidate)
    return kept


def extract_lh_notes(audio_path: str, max_voices: int = HARD_MAX_VOICES) -> list[NoteEvent]:
    """Run Basic Pitch on harmony audio (bass+other mix) and cap to
    max_voices concurrently-sounding notes. Unlike RH, deliberately keeps
    polyphony — real LH accompaniment is chordal, not a single line."""
    notes = transcribe_audio_to_notes(audio_path)
    return cap_simultaneous_notes(notes, max_voices)


def build_lh_part(notes: list[NoteEvent], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """Register-shift the capped transcription into HARD_LH_RANGE and
    build the LH 'Hard' Part — the full-detail base every difficulty tier
    derives from, same role as melody.extract.build_melody_part for RH."""
    part = notes_to_part(notes, part_id="LH", seconds_per_quarter=seconds_per_quarter)
    return shift_into_range(part, *HARD_LH_RANGE)
