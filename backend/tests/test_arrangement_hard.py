import pytest

from app.arrangement.hard import to_hard_lh
from app.arrangement.theory import ROOT_VELOCITY, INNER_VOICE_VELOCITY
from app.arrangement.types import ChordSymbol


def test_hard_lh_uses_a_full_block_chord_for_a_short_chord():
    # duration=0.5s is below SHORT_CHORD_THRESHOLD — a chopped-off arpeggio
    # would sound worse than one clean block-chord hit here
    chords = [ChordSymbol(start=0.0, duration=0.5, root=0, quality="major")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.pitch.midi)
    assert [n.pitch.midi for n in notes] == [36, 40, 43]  # C2, E2, G2 — full triad at once
    assert all(n.offset == 0.0 for n in notes)


def test_hard_lh_includes_the_seventh_in_a_short_chords_block_chord():
    chords = [ChordSymbol(start=0.0, duration=0.5, root=0, quality="dom7")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.pitch.midi)
    assert [n.pitch.midi for n in notes] == [36, 40, 43, 46]  # C2, E2, G2, Bb2 — 7th included


def test_hard_lh_arpeggiates_root_then_fifth_across_a_long_chord():
    # duration=3.0s is above SHORT_CHORD_THRESHOLD — long enough to arpeggiate
    chords = [ChordSymbol(start=0.0, duration=3.0, root=0, quality="major")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    assert [n.pitch.midi for n in notes[:4]] == [36, 43, 40, 43]  # root, 5th, 3rd, 5th


def test_hard_lh_lifts_every_fourth_arpeggio_cycle_an_octave_on_a_long_hold():
    # duration=4.0s = 16 eighth-note steps = exactly 4 Alberti cycles.
    # Repeating the same 4-note pattern unchanged for that long reads as
    # "the same chord playing over and over" — cycle 4 (the last one here)
    # lifts up an octave for variety.
    chords = [ChordSymbol(start=0.0, duration=4.0, root=0, quality="major")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    assert len(notes) == 16
    pitches = [n.pitch.midi for n in notes]
    assert pitches[:12] == [36, 43, 40, 43] * 3  # cycles 1-3 — unchanged
    assert pitches[12:16] == [48, 55, 52, 55]  # cycle 4 — lifted an octave


def test_hard_lh_arpeggio_step_offsets_respect_a_non_default_tempo():
    # duration=4.0s at 1.0 seconds-per-quarter (60 BPM) is a long chord
    # (still >= SHORT_CHORD_THRESHOLD in real seconds). Each eighth-note
    # step is ARPEGGIO_STEP(0.5) * seconds_per_quarter(1.0) = 0.5s wide,
    # so only 8 steps fit in 4.0s of real time, vs 16 at the default
    # 120 BPM tempo (0.25s-wide steps — see
    # test_hard_lh_lifts_every_fourth_arpeggio_cycle_an_octave_on_a_long_hold).
    chords = [ChordSymbol(start=0.0, duration=4.0, root=0, quality="major")]
    part = to_hard_lh(chords, seconds_per_quarter=1.0)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    assert len(notes) == 8


def test_hard_lh_accents_the_root_step_in_the_arpeggio():
    chords = [ChordSymbol(start=0.0, duration=3.0, root=0, quality="major")]
    part = to_hard_lh(chords)
    notes = sorted(part.flatten().notes, key=lambda n: n.offset)
    velocities = [n.volume.velocityScalar for n in notes[:4]]
    assert velocities == [
        pytest.approx(ROOT_VELOCITY),
        pytest.approx(INNER_VOICE_VELOCITY),
        pytest.approx(INNER_VOICE_VELOCITY),
        pytest.approx(INNER_VOICE_VELOCITY),
    ]


def test_hard_lh_accents_the_root_in_a_short_chords_block_chord():
    chords = [ChordSymbol(start=0.0, duration=0.5, root=0, quality="major")]
    part = to_hard_lh(chords)
    velocities = {n.pitch.midi: n.volume.velocityScalar for n in part.flatten().notes}
    assert velocities[36] == pytest.approx(ROOT_VELOCITY)
    assert velocities[40] == pytest.approx(INNER_VOICE_VELOCITY)
    assert velocities[43] == pytest.approx(INNER_VOICE_VELOCITY)
