import numpy as np
from scipy.io import wavfile

from app.arrange_pipeline import mix_wav_files


def test_mix_wav_files_sums_two_tones_without_clipping(tmp_path):
    sample_rate = 22050
    duration_s = 0.5
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)

    tone_a = (0.5 * np.sin(2 * np.pi * 220.0 * t) * 32767).astype(np.int16)
    tone_b = (0.5 * np.sin(2 * np.pi * 440.0 * t) * 32767).astype(np.int16)

    path_a = tmp_path / "a.wav"
    path_b = tmp_path / "b.wav"
    wavfile.write(str(path_a), sample_rate, tone_a)
    wavfile.write(str(path_b), sample_rate, tone_b)

    dest = tmp_path / "mixed.wav"
    result_path = mix_wav_files(path_a, path_b, dest)

    assert result_path == dest
    rate, mixed_audio = wavfile.read(str(dest))
    assert rate == sample_rate
    assert len(mixed_audio) == len(tone_a)
    assert np.max(np.abs(mixed_audio)) <= 32767
    assert np.max(np.abs(mixed_audio)) > 0  # not silent
