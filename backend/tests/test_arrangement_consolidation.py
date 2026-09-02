from app.arrangement.easy import to_easy_lh
from app.arrangement.hard import to_hard_lh
from app.arrangement.medium import MAX_BLOCK_TONES, to_medium_lh
from app.arrangement.theory import lh_voicing
from app.arrangement.types import ChordSymbol


def test_easy_note_is_lh_voicings_first_tone():
    # Consolidation contract: Easy's single note must be a literal read of
    # lh_voicing()'s tones, not an independently chosen pitch class — this
    # is what keeps the three tiers from silently re-diverging over time.
    chord = ChordSymbol(start=0.0, duration=1.0, root=0, quality="dom7")
    tones, _ = lh_voicing(chord, seconds_per_quarter=0.5)

    part = to_easy_lh([chord])
    played = {n.pitch.pitchClass for n in part.flatten().notes}
    assert played == {tones[0]}


def test_medium_block_chord_is_a_prefix_of_lh_voicings_tones():
    chord = ChordSymbol(start=0.0, duration=1.0, root=0, quality="dom7")
    tones, _ = lh_voicing(chord, seconds_per_quarter=0.5)

    part = to_medium_lh([chord])
    played = {n.pitch.pitchClass for n in part.flatten().notes}
    assert played == set(tones[:MAX_BLOCK_TONES])


def test_hard_uses_the_full_lh_voicing_tone_set_on_a_short_chord():
    chord = ChordSymbol(start=0.0, duration=0.5, root=0, quality="dom7")
    tones, is_short = lh_voicing(chord, seconds_per_quarter=0.5)
    assert is_short is True

    part = to_hard_lh([chord])
    played = {n.pitch.pitchClass for n in part.flatten().notes}
    assert played == set(tones)
