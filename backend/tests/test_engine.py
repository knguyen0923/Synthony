from music21 import stream, note

from app.notation.hand_split import get_hand_parts
from app.difficulty.engine import generate_variants


def test_generate_variants_returns_all_three_tiers_with_correct_hand_ids():
    rh = stream.Part(id="RH")
    rh.insert(0.0, note.Note("C4"))
    rh.insert(0.5, note.Note("D4"))
    lh = stream.Part(id="LH")
    lh.insert(0.0, note.Note("C3"))
    score = stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)

    variants = generate_variants(score)

    for variant_score in (variants.easy, variants.medium, variants.hard):
        variant_rh, variant_lh = get_hand_parts(variant_score)
        assert variant_rh.id == "RH"
        assert variant_lh.id == "LH"

    # Easy quantizes to a coarser grid than Hard, so it should never have
    # more notes than Hard for the same input.
    easy_rh, _ = get_hand_parts(variants.easy)
    hard_rh, _ = get_hand_parts(variants.hard)
    assert len(list(easy_rh.flatten().notes)) <= len(list(hard_rh.flatten().notes))
