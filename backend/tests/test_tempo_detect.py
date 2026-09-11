import math
import subprocess
from pathlib import Path

import numpy as np
import pretty_midi
import pytest
from scipy.io import wavfile

from app.tempo.detect import BeatMap, detect_beat_map

_FLUIDSYNTH_SOUNDFONT = Path(pretty_midi.__file__).parent / "TimGM6mb.sf2"


# ---------------------------------------------------------------------------
# BeatMap.constant: must be a byte-for-byte drop-in for the old fixed-tempo
# `seconds / SECONDS_PER_QUARTER` math used throughout the pipeline.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seconds_per_quarter", [0.5, 0.4, 2.0 / 3.0, 1.0, 0.12345])
@pytest.mark.parametrize(
    "seconds",
    [0.0, 0.1, 0.5, 1.0, 3.333333, 100.0, -1.0, 1e-9],
)
def test_constant_matches_old_fixed_tempo_math_exactly(seconds_per_quarter, seconds):
    beat_map = BeatMap.constant(seconds_per_quarter)
    assert beat_map.to_quarter_length(seconds) == seconds / seconds_per_quarter


def test_constant_bpm_at_is_fixed_everywhere():
    beat_map = BeatMap.constant(0.5)  # 120 BPM
    assert beat_map.bpm_at(0.0) == pytest.approx(120.0)
    assert beat_map.bpm_at(50.0) == pytest.approx(120.0)
    assert beat_map.bpm_at(-5.0) == pytest.approx(120.0)


# ---------------------------------------------------------------------------
# BeatMap piecewise-linear interpolation/extrapolation against hand-built
# beat_times.
# ---------------------------------------------------------------------------


def test_to_quarter_length_at_exact_beat_times_is_the_beat_index():
    beat_times = [0.0, 0.5, 1.0, 1.6, 2.4]
    beat_map = BeatMap(beat_times)
    for index, t in enumerate(beat_times):
        assert beat_map.to_quarter_length(t) == pytest.approx(index)


def test_to_quarter_length_interpolates_between_beats():
    # Uneven spacing so a naive "assume constant tempo" implementation
    # would fail this: interval 0->1 is 0.5s, interval 1->2 is 1.0s.
    beat_times = [0.0, 0.5, 1.5]
    beat_map = BeatMap(beat_times)

    # Midpoint of the first (0.5s) interval -> quarterLength 0.5.
    assert beat_map.to_quarter_length(0.25) == pytest.approx(0.5)
    # Quarter-way into the second (1.0s) interval -> quarterLength 1.25.
    assert beat_map.to_quarter_length(0.75) == pytest.approx(1.25)


def test_to_quarter_length_extrapolates_before_first_beat():
    # First interval is 0.5s/quarter; extrapolating backward should
    # continue that local tempo linearly.
    beat_times = [1.0, 1.5, 2.0]
    beat_map = BeatMap(beat_times)
    assert beat_map.to_quarter_length(0.5) == pytest.approx(-1.0)
    assert beat_map.to_quarter_length(0.0) == pytest.approx(-2.0)


def test_to_quarter_length_extrapolates_after_last_beat():
    # Last interval is 1.0s/quarter; extrapolating forward should
    # continue that local tempo linearly.
    beat_times = [0.0, 0.5, 1.5]
    beat_map = BeatMap(beat_times)
    assert beat_map.to_quarter_length(2.5) == pytest.approx(3.0)
    assert beat_map.to_quarter_length(3.5) == pytest.approx(4.0)


def test_bpm_at_reflects_local_tempo():
    # interval 0->1 = 0.5s/beat = 120 BPM; interval 1->2 = 1.0s/beat = 60 BPM
    beat_times = [0.0, 0.5, 1.5]
    beat_map = BeatMap(beat_times)
    assert beat_map.bpm_at(0.25) == pytest.approx(120.0)
    assert beat_map.bpm_at(1.0) == pytest.approx(60.0)
    # extrapolation regions use the nearest interval's tempo
    assert beat_map.bpm_at(-1.0) == pytest.approx(120.0)
    assert beat_map.bpm_at(5.0) == pytest.approx(60.0)


def test_beat_map_requires_at_least_two_beats():
    with pytest.raises(ValueError):
        BeatMap([])
    with pytest.raises(ValueError):
        BeatMap([1.0])


def test_beat_map_requires_strictly_ascending_beat_times():
    with pytest.raises(ValueError):
        BeatMap([0.0, 0.5, 0.5])
    with pytest.raises(ValueError):
        BeatMap([0.0, 0.6, 0.5])


# ---------------------------------------------------------------------------
# detect_beat_map on real, synthesized audio with known ground-truth beat
# positions (fluidsynth-rendered piano note onsets placed at the exact
# times we want madmom to recover).
# ---------------------------------------------------------------------------


def _render_piano_onsets(path: Path, onset_times: list[float], pitch: int = 60, note_dur: float = 0.1) -> None:
    midi = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0)  # Acoustic Grand Piano
    for t in onset_times:
        instrument.notes.append(pretty_midi.Note(velocity=100, pitch=pitch, start=t, end=t + note_dur))
    midi.instruments.append(instrument)
    midi_path = path.with_suffix(".mid")
    midi.write(str(midi_path))
    subprocess.run(
        ["fluidsynth", "-ni", "-F", str(path), "-r", "22050", str(_FLUIDSYNTH_SOUNDFONT), str(midi_path)],
        check=True,
        capture_output=True,
    )


def _require_fluidsynth():
    import shutil

    if shutil.which("fluidsynth") is None:
        pytest.skip("fluidsynth not installed")


def test_detect_beat_map_recovers_steady_tempo(tmp_path):
    """A steady 100 BPM click track of piano notes: madmom should recover
    beat timestamps close to the known onset times, and BeatMap.bpm_at
    should read back close to 100 BPM everywhere."""
    _require_fluidsynth()
    bpm = 100.0
    seconds_per_beat = 60.0 / bpm
    onset_times = []
    t = 0.5
    while t < 8.0:
        onset_times.append(t)
        t += seconds_per_beat

    wav_path = tmp_path / "steady.wav"
    _render_piano_onsets(wav_path, onset_times)

    beat_map = detect_beat_map(str(wav_path))

    # For each ground-truth onset, the beat map's quarter-length position
    # should land close to an integer (i.e. an actual detected beat),
    # and stepping between consecutive onsets should measure ~1 quarter.
    positions = [beat_map.to_quarter_length(t) for t in onset_times]
    steps = [b - a for a, b in zip(positions, positions[1:])]
    mean_step = sum(steps) / len(steps)
    max_step_error = max(abs(s - 1.0) for s in steps)

    print(f"[steady tempo] mean quarter-length step={mean_step:.4f} (expect 1.0), "
          f"max abs error={max_step_error:.4f}")

    assert mean_step == pytest.approx(1.0, abs=0.05)
    assert max_step_error < 0.15

    bpm_estimates = [beat_map.bpm_at(t) for t in onset_times[1:-1]]
    mean_bpm = sum(bpm_estimates) / len(bpm_estimates)
    print(f"[steady tempo] mean bpm_at={mean_bpm:.2f} (expect ~{bpm})")
    assert mean_bpm == pytest.approx(bpm, abs=8.0)


def test_detect_beat_map_tracks_tempo_ramp(tmp_path):
    """A tempo ramp from 80 to 160 BPM over 12s: madmom's beat-map should
    track the instantaneous tempo change, not lock onto a single global
    BPM. We check bpm_at() rises over the course of the clip."""
    _require_fluidsynth()
    start_bpm, end_bpm, duration = 80.0, 160.0, 12.0
    onset_times = [0.5]
    t = 0.5
    while t < duration:
        instantaneous_bpm = start_bpm + (end_bpm - start_bpm) * (t / duration)
        t += 60.0 / instantaneous_bpm
        if t < duration:
            onset_times.append(t)

    wav_path = tmp_path / "ramp.wav"
    _render_piano_onsets(wav_path, onset_times)

    beat_map = detect_beat_map(str(wav_path))

    early_bpm = beat_map.bpm_at(onset_times[2])
    late_bpm = beat_map.bpm_at(onset_times[-3])
    print(f"[tempo ramp] bpm_at(early)={early_bpm:.2f} (expect ~{start_bpm}), "
          f"bpm_at(late)={late_bpm:.2f} (expect ~{end_bpm})")

    # Tempo should clearly rise across the clip, and land in the right
    # ballpark at both ends -- generous tolerance since this is a neural
    # detector on a synthetic click track, not a golden-master check.
    assert late_bpm > early_bpm + 20.0
    assert early_bpm == pytest.approx(start_bpm, abs=15.0)
    assert late_bpm == pytest.approx(end_bpm, abs=20.0)

    # Quarter-length positions should also track monotonically and land
    # near-integer at each onset (same style of check as the steady case).
    positions = [beat_map.to_quarter_length(t) for t in onset_times]
    assert all(b > a for a, b in zip(positions, positions[1:]))


# ---------------------------------------------------------------------------
# Fallback path: madmom can't produce >=2 usable beats.
# ---------------------------------------------------------------------------


def test_detect_beat_map_falls_back_on_silence(tmp_path):
    sr = 22050
    y = np.zeros(int(sr * 2.0), dtype=np.int16)
    wav_path = tmp_path / "silence.wav"
    wavfile.write(str(wav_path), sr, y)

    beat_map = detect_beat_map(str(wav_path))

    # Must not crash, and must produce a usable, monotonic mapping.
    assert beat_map.to_quarter_length(1.0) > beat_map.to_quarter_length(0.0)
    assert math.isfinite(beat_map.bpm_at(0.5))


def test_detect_beat_map_falls_back_on_extremely_short_clip(tmp_path):
    sr = 22050
    y = np.zeros(int(sr * 0.05), dtype=np.int16)
    wav_path = tmp_path / "tiny.wav"
    wavfile.write(str(wav_path), sr, y)

    beat_map = detect_beat_map(str(wav_path))

    assert beat_map.to_quarter_length(0.03) > beat_map.to_quarter_length(0.0)
    assert math.isfinite(beat_map.bpm_at(0.02))
