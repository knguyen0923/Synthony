import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pretty_midi
import pytest
from scipy.io import wavfile

import app.logging_config as logging_config_module
import app.storage as storage_module

_FLUIDSYNTH_SOUNDFONT = Path(pretty_midi.__file__).parent / "TimGM6mb.sf2"

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

# Same isolation, same reasoning, for the rotating file handler's log
# directory: app.main's module-level configure_logging() call (and any
# test that reloads it) would otherwise write into the real
# backend/logs/app.log, polluting the one file meant to be a durable
# crash-diagnosis trail with test noise. Individual tests in
# test_logging_config.py further monkeypatch LOG_DIR per-test (overriding
# this default) to assert on rotation/fallback behavior in isolation.
_TEST_LOG_DIR = Path(tempfile.mkdtemp(prefix="synthony-test-logs-"))
logging_config_module.LOG_DIR = _TEST_LOG_DIR


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


@pytest.fixture
def synthetic_piano_note_wav(tmp_path):
    """A real Acoustic Grand Piano rendering (via fluidsynth) of a single
    held A4 note. Unlike synthetic_piano_wav's bare sine tone, this has an
    actual piano attack/harmonic envelope — needed for models trained on
    real piano timbre (a pure sine has no attack transient and such models
    may not fire on it at all). Skips if fluidsynth isn't on PATH."""
    if shutil.which("fluidsynth") is None:
        pytest.skip("fluidsynth not installed")

    midi = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(program=0)  # Acoustic Grand Piano
    instrument.notes.append(pretty_midi.Note(velocity=100, pitch=69, start=0.1, end=1.5))
    midi.instruments.append(instrument)
    midi_path = tmp_path / "synthetic_piano_note.mid"
    midi.write(str(midi_path))

    wav_path = tmp_path / "synthetic_piano_note.wav"
    subprocess.run(
        ["fluidsynth", "-ni", "-F", str(wav_path), "-r", "22050", str(_FLUIDSYNTH_SOUNDFONT), str(midi_path)],
        check=True,
        capture_output=True,
    )
    return wav_path


@pytest.fixture(autouse=True)
def clean_storage():
    yield
    # Only ever clears the isolated test storage root set up above, never the
    # real backend/storage/ directory used by a running backend.
    if storage_module.STORAGE_ROOT.exists():
        shutil.rmtree(storage_module.STORAGE_ROOT)
    storage_module.STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
