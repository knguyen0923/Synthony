from app.notation.types import NoteEvent


def cap_simultaneous_notes(notes: list[NoteEvent], max_voices: int) -> list[NoteEvent]:
    """At every moment, keep at most max_voices concurrently-sounding
    notes — the highest-velocity ones — discarding the rest. Used both for
    Spec 2's LH extraction (Basic Pitch on a busy 'other' stem can
    over-detect beyond what a hand can physically play) and, more
    generally, for any hand's assigned notes after app.notation.
    hand_assignment.assign_hands — a piano transcription model's offset
    (release) time reflects acoustic decay, which under sustain pedal can
    extend a note's written duration far past when the key was actually
    released, piling up many notes that don't overlap in reality into an
    unplayable-looking simultaneous stack. Generalizes
    melody.extract.reduce_to_monophonic (confidence-over-raw-detection)
    from 1 voice to N. On a tie, the earlier-processed (already-held) note
    wins."""
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
        held = [n for n in held if n is not weakest]
        kept = [n for n in kept if n is not weakest]
        held.append(candidate)
        kept.append(candidate)
    return kept
