import copy

from music21 import stream

from app.notation.hand_split import carry_clef


def quantize_part(part: stream.Part, grid: float, max_voices: int = 1) -> stream.Part:
    """Snap note onsets to the given grid (in quarterLength units),
    keeping at most max_voices notes per slot. At max_voices=1 (the
    default, and RH's only call site), keeps whichever note was
    encountered first per slot, exactly as before. Above 1, keeps the
    highest-velocity notes among all notes whose onset falls in the slot
    (deduping repeated pitch classes to their higher-velocity instance
    first) — used for LH's polyphonic Easy/Medium reduction, where
    "first encountered" isn't a meaningful tie-break the way it is for a
    single melody line."""
    by_slot: dict[float, list] = {}
    for element in part.flatten().notes:
        slot = (element.offset // grid) * grid
        by_slot.setdefault(slot, []).append(element)

    quantized = stream.Part(id=part.id)
    for slot in sorted(by_slot):
        candidates = by_slot[slot]
        kept = [candidates[0]] if max_voices == 1 else _cap_voices(candidates, max_voices)
        for element in kept:
            new_element = copy.deepcopy(element)
            new_element.duration.quarterLength = grid
            quantized.insert(slot, new_element)

    carry_clef(part, quantized)
    return quantized


def _cap_voices(candidates: list, max_voices: int) -> list:
    """Dedup by pitch class (keeping the higher-velocity instance of
    each), then cap at max_voices, highest-velocity first."""
    by_pitch_class: dict[int, object] = {}
    for element in candidates:
        pitch_class = element.pitch.pitchClass
        existing = by_pitch_class.get(pitch_class)
        if existing is None or element.volume.velocityScalar > existing.volume.velocityScalar:
            by_pitch_class[pitch_class] = element
    ordered = sorted(by_pitch_class.values(), key=lambda n: n.volume.velocityScalar, reverse=True)
    return ordered[:max_voices]
