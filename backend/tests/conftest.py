import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest
from scipy.io import wavfile

import app.storage as storage_module

# Redirect STORAGE_ROOT to an isolated, session-scoped temp directory *before*
# any test module (and, critically, app.main — which mounts a StaticFiles
# directory and mkdir()s STORAGE_ROOT at import time) gets imported. conftest.py
# is loaded by pytest before it collects/imports the test modules in this
# directory, so this assignment is visible to every later `from app.storage
# import STORAGE_ROOT` and to app.main's module-level use of it.
#
# This is what makes the test suite safe to run against a real, populated
# backend/storage/ directory: tests never touch the real STORAGE_ROOT at all.
_TEST_STORAGE_ROOT = Path(tempfile.mkdtemp(prefix="synthony-test-storage-"))
storage_module.STORAGE_ROOT = _TEST_STORAGE_ROOT


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
    # Only ever clears the isolated test storage root set up above, never the
    # real backend/storage/ directory used by a running backend.
    if storage_module.STORAGE_ROOT.exists():
        shutil.rmtree(storage_module.STORAGE_ROOT)
    storage_module.STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
