import copy

from music21 import clef, stream

from app.notation.hand_split import get_hand_parts, build_grand_staff_score, get_title
from app.difficulty.quantize import quantize_part
from app.difficulty.range_shift import shift_into_range

EASY_GRID = 1.0            # quarter note
EASY_RH_RANGE = (60, 72)   # one octave, C4-C5
EASY_LH_RANGE = (36, 48)   # one octave, C2-C3


def to_easy(score: stream.Score) -> stream.Score:
    rh, lh = get_hand_parts(score)

    rh_quantized = quantize_part(rh, EASY_GRID)
    lh_root = _reduce_to_root_per_slot(lh, EASY_GRID)

    rh_ranged = shift_into_range(rh_quantized, *EASY_RH_RANGE)
    lh_ranged = shift_into_range(lh_root, *EASY_LH_RANGE)

    for part in (rh_ranged, lh_ranged):
        for element in part.flatten().notes:
            element.pitch.simplifyEnharmonic(inPlace=True)

    return build_grand_staff_score(rh_ranged, lh_ranged, title=get_title(score))


def _reduce_to_root_per_slot(lh_part: stream.Part, grid: float) -> stream.Part:
    """Keep only the lowest-pitched note in each grid slot, as the root
    bass note."""
    by_slot: dict[float, list] = {}
    for element in lh_part.flatten().notes:
        slot = (element.offset // grid) * grid
        by_slot.setdefault(slot, []).append(element)

    reduced = stream.Part(id=lh_part.id)
    for slot in sorted(by_slot):
        lowest = min(by_slot[slot], key=lambda n: n.pitch.midi)
        new_element = copy.deepcopy(lowest)
        new_element.duration.quarterLength = grid
        reduced.insert(slot, new_element)

    # Preserve any clef from the input part
    for c in lh_part.getElementsByClass(clef.Clef):
        reduced.insert(0, copy.deepcopy(c))

    return reduced
