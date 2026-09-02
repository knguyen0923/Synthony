"""Regression tests for a real bug found running the full pipeline against
a real song: chord timings from beat-tracking are irregular floats (e.g.
1.869206349206349s), and without quantization these produce quarterLength
fractions (e.g. 256/3675) that MusicXML cannot express, crashing export
with "Cannot convert inexpressible durations to MusicXML." All three
arrangement tiers must round offsets/durations to a MusicXML-safe grid,
the same constraint app.notation.hand_split already applies to
audio-derived note timing."""

from pathlib import Path
from tempfile import TemporaryDirectory

from app.arrangement.easy import to_easy_lh
from app.arrangement.hard import to_hard_lh
from app.arrangement.medium import to_medium_lh
from app.arrangement.types import ChordSymbol
from app.export import export_musicxml
from app.notation.hand_split import NOTATION_GRID, build_grand_staff_score
from music21 import stream

# Real chord durations detected from an actual song during end-to-end
# testing — irregular floats, not the clean round numbers the original
# unit tests used.
IRREGULAR_CHORDS = [
    ChordSymbol(start=0.0, duration=0.034829931972789115, root=0, quality="major"),
    ChordSymbol(start=0.034829931972789115, duration=1.869206349206349, root=4, quality="min7"),
    ChordSymbol(start=1.9040362811791383, duration=1.7298866213151927, root=7, quality="major"),
    ChordSymbol(start=3.633922902494331, duration=3.227573696145125, root=0, quality="major"),
]


def _assert_on_grid(value: float) -> None:
    steps = value / NOTATION_GRID
    assert abs(steps - round(steps)) < 1e-6, f"{value} is not a multiple of NOTATION_GRID ({NOTATION_GRID})"


def _assert_part_is_grid_aligned(part: stream.Part) -> None:
    for element in part.flatten().notes:
        _assert_on_grid(element.offset)
        _assert_on_grid(element.duration.quarterLength)
        assert element.duration.quarterLength > 0


def test_easy_lh_offsets_and_durations_are_grid_aligned():
    _assert_part_is_grid_aligned(to_easy_lh(IRREGULAR_CHORDS))


def test_medium_lh_offsets_and_durations_are_grid_aligned():
    _assert_part_is_grid_aligned(to_medium_lh(IRREGULAR_CHORDS))


def test_hard_lh_offsets_and_durations_are_grid_aligned():
    _assert_part_is_grid_aligned(to_hard_lh(IRREGULAR_CHORDS))


def test_each_tier_exports_to_musicxml_without_raising():
    rh = stream.Part(id="RH")

    for lh in (to_easy_lh(IRREGULAR_CHORDS), to_medium_lh(IRREGULAR_CHORDS), to_hard_lh(IRREGULAR_CHORDS)):
        score = build_grand_staff_score(rh.__class__(id="RH"), lh, title="Regression")
        with TemporaryDirectory() as tmpdir:
            export_musicxml(score, Path(tmpdir) / "out.musicxml")
