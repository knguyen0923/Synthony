import subprocess
from pathlib import Path

import numpy as np
import pretty_midi
import pytest
from scipy.io import wavfile

from app.tempo.time_signature import (
    _bar_lengths_from_downbeats,
    _consistent_bar_length,
    detect_time_signature,
)

_FLUIDSYNTH_SOUNDFONT = Path(pretty_midi.__file__).parent / "TimGM6mb.sf2"


# ---------------------------------------------------------------------------
# Pure logic: bar-splitting and the confidence/agreement threshold. No audio
# involved -- fast, deterministic.
# ---------------------------------------------------------------------------


def test_bar_lengths_from_clean_4_4_pattern():
    positions = [4, 1, 2, 3, 4, 1, 2, 3, 4, 1, 2, 3, 4]
    assert _bar_lengths_from_downbeats(positions) == [4, 4]


def test_bar_lengths_from_clean_3_4_pattern():
    # 3 downbeats ("1"s) define 2 complete bars between them (the leading
    # partial bar and the trailing partial bar past the last downbeat are
    # both excluded).
    positions = [3, 1, 2, 3, 1, 2, 3, 1, 2, 3]
    assert _bar_lengths_from_downbeats(positions) == [3, 3]


def test_bar_lengths_empty_when_no_downbeats_detected():
    assert _bar_lengths_from_downbeats([2, 3, 4]) == []


def test_bar_lengths_empty_when_only_one_downbeat():
    # A single "1" has no following downbeat to close a bar against.
    assert _bar_lengths_from_downbeats([1, 2, 3, 4]) == []


def test_consistent_bar_length_returns_mode_when_agreement_is_unanimous():
    assert _consistent_bar_length([4, 4, 4, 4, 4], min_bars=4, min_agreement=0.9) == 4


def test_consistent_bar_length_returns_none_when_too_few_bars():
    assert _consistent_bar_length([3, 3, 3], min_bars=4, min_agreement=0.9) is None


def test_consistent_bar_length_returns_none_when_agreement_too_low():
    # 3 of 5 = 60% agreement, below the 90% bar.
    assert _consistent_bar_length([4, 4, 4, 3, 3], min_bars=4, min_agreement=0.9) is None


def test_consistent_bar_length_returns_mode_at_exact_threshold():
    # 9 of 10 = exactly 90%.
    bars = [4] * 9 + [3]
    assert _consistent_bar_length(bars, min_bars=4, min_agreement=0.9) == 4


# ---------------------------------------------------------------------------
# detect_time_signature on real, synthesized audio.
#
# A plain click track of identical-velocity onsets (the style
# test_tempo_detect.py's beat-tracking tests use) turned out to be too
# quiet on average for has_audible_signal's RMS gate -- confirmed directly:
# both a synthesized 4/4 and 3/4 click track measured well under the 0.01
# RMS floor, so detect_time_signature was silently taking its "inaudible"
# fallback path rather than actually exercising downbeat detection (one
# clip's result looked right purely by coincidence, since the fallback and
# the correct answer happened to match). Fixed by peak-normalizing the
# rendered audio before writing it -- real songs are continuously loud, so
# this quirk is specific to sparse synthetic click tracks, not something
# detect_time_signature itself needs to handle.
# ---------------------------------------------------------------------------


def _require_fluidsynth():
    import shutil

    if shutil.which("fluidsynth") is None:
        pytest.skip("fluidsynth not installed")


def _render_accented_click_track(path: Path, beat_velocities: list[int], bpm: float, n_bars: int) -> None:
    """Renders n_bars repetitions of beat_velocities (one bar's velocity
    pattern, first entry = downbeat) at the given tempo, then peak-
    normalizes the result so it clears has_audible_signal's RMS gate --
    see the module docstring above for why that's necessary here."""
    seconds_per_beat = 60.0 / bpm
    note_dur = seconds_per_beat * 0.85
    midi = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0)
    t = 0.5
    for _ in range(n_bars):
        for velocity in beat_velocities:
            instrument.notes.append(pretty_midi.Note(velocity=velocity, pitch=60, start=t, end=t + note_dur))
            t += seconds_per_beat
    midi.instruments.append(instrument)
    midi_path = path.with_suffix(".mid")
    midi.write(str(midi_path))
    subprocess.run(
        ["fluidsynth", "-ni", "-F", str(path), "-r", "22050", str(_FLUIDSYNTH_SOUNDFONT), str(midi_path)],
        check=True,
        capture_output=True,
    )

    sr, y = wavfile.read(str(path))
    y = y.astype(np.float64)
    peak = np.max(np.abs(y))
    if peak > 0:
        gain = (0.9 * 32767) / peak
        y = np.clip(y * gain, -32768, 32767).astype(np.int16)
        wavfile.write(str(path), sr, y)


def test_detect_time_signature_recognizes_4_4(tmp_path):
    _require_fluidsynth()
    wav_path = tmp_path / "four_four.wav"
    _render_accented_click_track(wav_path, beat_velocities=[120, 70, 90, 70], bpm=120, n_bars=24)

    result = detect_time_signature(str(wav_path))

    assert result.ratioString == "4/4"


def test_detect_time_signature_recognizes_3_4(tmp_path):
    _require_fluidsynth()
    wav_path = tmp_path / "three_four.wav"
    _render_accented_click_track(wav_path, beat_velocities=[120, 70, 70], bpm=150, n_bars=24)

    result = detect_time_signature(str(wav_path))

    assert result.ratioString == "3/4"


def test_detect_time_signature_falls_back_to_4_4_on_silence(tmp_path):
    sr = 22050
    y = np.zeros(int(sr * 4.0), dtype=np.int16)
    wav_path = tmp_path / "silence.wav"
    wavfile.write(str(wav_path), sr, y)

    result = detect_time_signature(str(wav_path))

    assert result.ratioString == "4/4"
