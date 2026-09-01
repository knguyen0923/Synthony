import copy

from music21 import clef, stream

from app.notation.hand_split import get_hand_parts, build_grand_staff_score, get_title
from app.difficulty.quantize import quantize_part
from app.difficulty.range_shift import shift_into_range

MEDIUM_GRID = 0.5          # eighth note
MEDIUM_RH_RANGE = (55, 79) # roughly two octaves, G3-G5
MEDIUM_LH_RANGE = (36, 55) # C2-G3
MAX_VOICING_TONES = 3


def to_medium(score: stream.Score) -> stream.Score:
    rh, lh = get_hand_parts(score)

    rh_quantized = quantize_part(rh, MEDIUM_GRID)
    lh_voiced = _voice_chords_per_slot(lh, MEDIUM_GRID)

    rh_ranged = shift_into_range(rh_quantized, *MEDIUM_RH_RANGE)
    lh_ranged = shift_into_range(lh_voiced, *MEDIUM_LH_RANGE)

    return build_grand_staff_score(rh_ranged, lh_ranged, title=get_title(score))


def _voice_chords_per_slot(lh_part: stream.Part, grid: float) -> stream.Part:
    by_slot: dict[float, list] = {}
    for element in lh_part.flatten().notes:
        slot = (element.offset // grid) * grid
        by_slot.setdefault(slot, []).append(element)

    voiced = stream.Part(id=lh_part.id)
    for slot in sorted(by_slot):
        for tone in _reduce_to_voicing(by_slot[slot]):
            new_element = copy.deepcopy(tone)
            new_element.duration.quarterLength = grid
            voiced.insert(slot, new_element)

    # Preserve any clef from the input part
    for c in lh_part.getElementsByClass(clef.Clef):
        voiced.insert(0, copy.deepcopy(c))

    return voiced


def _reduce_to_voicing(notes: list) -> list:
    """Drop doubled pitch classes (keeping the lowest instance of each),
    then cap at MAX_VOICING_TONES tones, lowest first."""
    by_pitch_class: dict[int, object] = {}
    for n in notes:
        pitch_class = n.pitch.pitchClass
        existing = by_pitch_class.get(pitch_class)
        if existing is None or n.pitch.midi < existing.pitch.midi:
            by_pitch_class[pitch_class] = n

    ordered = sorted(by_pitch_class.values(), key=lambda n: n.pitch.midi)
    return ordered[:MAX_VOICING_TONES]
