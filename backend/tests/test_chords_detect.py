import pytest

from app.chords.detect import _tempo_to_seconds_per_quarter, detect_key_and_tempo


def test_tempo_to_seconds_per_quarter_converts_bpm():
    assert _tempo_to_seconds_per_quarter(120.0) == 0.5
    assert _tempo_to_seconds_per_quarter(60.0) == 1.0


def test_tempo_to_seconds_per_quarter_clamps_extreme_values():
    assert _tempo_to_seconds_per_quarter(20.0) == 60.0 / 60.0   # clamped up to MIN_TEMPO_BPM
    assert _tempo_to_seconds_per_quarter(500.0) == 60.0 / 200.0  # clamped down to MAX_TEMPO_BPM


def test_tempo_to_seconds_per_quarter_falls_back_on_zero_or_none():
    assert _tempo_to_seconds_per_quarter(0.0) == 0.5
    assert _tempo_to_seconds_per_quarter(None) == 0.5


def test_detect_key_and_tempo_returns_a_key_and_positive_tempo(synthetic_piano_wav):
    key, seconds_per_quarter = detect_key_and_tempo(str(synthetic_piano_wav))
    tonic, mode = key
    assert 0 <= tonic <= 11
    assert mode in ("major", "minor")
    assert seconds_per_quarter > 0
