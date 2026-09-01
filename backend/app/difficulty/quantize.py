import copy

from music21 import clef, stream


def quantize_part(part: stream.Part, grid: float) -> stream.Part:
    """Snap note onsets to the given grid (in quarterLength units). Keeps
    only the first note whose onset falls in each grid slot; drops the
    rest."""
    quantized = stream.Part(id=part.id)
    seen_slots: set[float] = set()

    for element in part.flatten().notes:
        slot = (element.offset // grid) * grid
        if slot in seen_slots:
            continue
        seen_slots.add(slot)

        new_element = copy.deepcopy(element)
        new_element.duration.quarterLength = grid
        quantized.insert(slot, new_element)

    # Preserve any clef from the input part
    for c in part.getElementsByClass(clef.Clef):
        quantized.insert(0, copy.deepcopy(c))

    return quantized
