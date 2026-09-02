from app.arrangement.engine import generate_lh_variants
from app.arrangement.types import ChordSymbol


def test_generate_lh_variants_produces_all_three_tiers():
    chords = [ChordSymbol(start=0.0, duration=1.0, root=0, quality="major")]
    variants = generate_lh_variants(chords)
    assert len(list(variants.easy.flatten().notes)) == 1
    assert len(list(variants.medium.flatten().notes)) == 3
    assert len(list(variants.hard.flatten().notes)) == 4
