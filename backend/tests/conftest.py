import shutil

import numpy as np
import pytest
from scipy.io import wavfile

from app.storage import STORAGE_ROOT


@pytest.fixture
def synthetic_piano_wav(tmp_path):
    """A short synthetic WAV: a single held A4 (440Hz) tone, 2 seconds."""
    sample_rate = 22050
    duration_s = 2.0
    frequency_hz = 440.0

    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    tone = 0.5 * np.sin(2 * np.pi * frequency_hz * t)
    audio = (tone * 32767).astype(np.int16)

    wav_path = tmp_path / "synthetic_piano.wav"
    wavfile.write(str(wav_path), sample_rate, audio)
    return wav_path


@pytest.fixture(autouse=True)
def clean_storage():
    yield
    if STORAGE_ROOT.exists():
        shutil.rmtree(STORAGE_ROOT)
