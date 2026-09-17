"""Tests for metrics.score_plausibility(). Loads quality_harness/metrics.py
by explicit file path (not `from metrics import ...`) because
scripts/ground_truth_eval/ has its own unrelated metrics.py -- pytest
caches bare module names in sys.modules, so two same-named modules in
different directories can silently resolve to the wrong one depending on
collection order (confirmed directly: a naive `from metrics import x` in
this file previously raised ImportError pointing at
ground_truth_eval/metrics.py instead)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "quality_harness_metrics", Path(__file__).parent / "metrics.py"
)
metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(metrics)

score_plausibility = metrics.score_plausibility


def _part(note_count, duration_quarter_length=None, peak_simultaneous_voices=1,
          short_note_count=0, below_middle_c=0, at_or_above_middle_c=None):
    """Builds a minimal analyze_part()-shaped dict with just the fields
    score_plausibility reads."""
    if at_or_above_middle_c is None:
        at_or_above_middle_c = note_count - below_middle_c
    duration_histogram = {}
    if short_note_count:
        duration_histogram["<16th (<0.25ql)"] = short_note_count
    return {
        "note_count": note_count,
        "duration_quarter_length": duration_quarter_length if duration_quarter_length is not None else max(note_count, 1),
        "voice_count": {"peak_simultaneous_voices": peak_simultaneous_voices},
        "duration_histogram": duration_histogram,
        "register_split": {
            "below_middle_c": below_middle_c,
            "at_or_above_middle_c": at_or_above_middle_c,
        },
    }


def _parts(rh_note_count, lh_note_count, rh=None, lh=None):
    """A clean-pass RH/LH pair by default (RH entirely at/above middle C,
    LH entirely below -- no register overlap); pass rh={...}/lh={...}
    overrides (any _part() kwarg) to shape a specific scenario."""
    lh_kwargs = dict(lh or {})
    lh_kwargs.setdefault("below_middle_c", lh_note_count)
    rh_part = _part(rh_note_count, **(rh or {}))
    lh_part = _part(lh_note_count, **lh_kwargs)
    return {"Right Hand": rh_part, "Left Hand": lh_part}


def test_clean_pass_flags_nothing():
    # Clean pair: RH entirely at/above middle C, LH entirely below -- no overlap.
    parts = _parts(rh_note_count=100, lh_note_count=100)
    assert score_plausibility(parts) == []


def test_hand_balance_flags_when_one_hand_has_under_10_percent():
    # Shaped like Big Rock's real historical defect: RH 1169, LH 29 (~2.4%).
    parts = _parts(rh_note_count=1169, lh_note_count=29)
    issues = score_plausibility(parts)
    assert any(i["check"] == "hand_balance" for i in issues)


def test_register_overlap_flags_rh_notes_mostly_in_bass_register():
    parts = _parts(rh_note_count=100, lh_note_count=100,
                    rh={"below_middle_c": 40})  # 40% of RH below middle C
    issues = score_plausibility(parts)
    assert any(i["check"] == "register_overlap" and i["part"] == "Right Hand" for i in issues)


def test_register_overlap_flags_lh_notes_mostly_above_middle_c():
    parts = _parts(rh_note_count=100, lh_note_count=100,
                    lh={"below_middle_c": 60, "at_or_above_middle_c": 40})  # 40% of LH above middle C
    issues = score_plausibility(parts)
    assert any(i["check"] == "register_overlap" and i["part"] == "Left Hand" for i in issues)


def test_note_duration_sanity_flags_excess_short_notes():
    parts = _parts(rh_note_count=100, lh_note_count=100, rh={"short_note_count": 45})
    issues = score_plausibility(parts)
    assert any(i["check"] == "note_duration_sanity" and i["part"] == "Right Hand" for i in issues)


def test_voice_count_sanity_flags_over_6_simultaneous_notes():
    parts = _parts(rh_note_count=100, lh_note_count=100, lh={"peak_simultaneous_voices": 7})
    issues = score_plausibility(parts)
    assert any(i["check"] == "voice_count_sanity" and i["part"] == "Left Hand" for i in issues)


def test_note_density_sanity_flags_near_silent_part():
    parts = _parts(rh_note_count=100, lh_note_count=100,
                    rh={"duration_quarter_length": 10000})  # 0.01 notes/ql
    issues = score_plausibility(parts)
    assert any(i["check"] == "note_density_sanity" and i["part"] == "Right Hand" for i in issues)


def test_note_density_sanity_flags_implausibly_dense_part():
    parts = _parts(rh_note_count=1000, lh_note_count=100,
                    rh={"duration_quarter_length": 100})  # 10 notes/ql
    issues = score_plausibility(parts)
    assert any(i["check"] == "note_density_sanity" and i["part"] == "Right Hand" for i in issues)
