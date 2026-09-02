import pytest
import numpy as np
from scipy.io import wavfile

from app.arrange_pipeline import _lh_variants, mix_wav_files
from app.notation.types import NoteEvent


def test_lh_variants_raises_when_no_harmonic_content_detected(monkeypatch):
    # New behavior specific to _lh_variants (unlike _rh_variants, which has
    # no equivalent guard) — a song whose harmony stem transcribes to
    # nothing must fail loudly rather than silently produce an empty LH
    # part, the same "fail the job, don't ship broken output" contract
    # run_arrange_pipeline already relies on for its try/except.
    import app.arrange_pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "extract_lh_notes", lambda audio_path: [])

    with pytest.raises(ValueError, match="No harmonic content detected"):
        _lh_variants("fake/harmony.wav")


def test_lh_variants_produces_all_three_tiers_with_decreasing_voice_counts(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    # Two simultaneous chord tones, held long enough that Easy/Medium's
    # coarser grid still lands an onset inside the note.
    fake_notes = [
        NoteEvent(start=0.0, end=2.0, pitch=48, velocity=0.9),  # root
        NoteEvent(start=0.0, end=2.0, pitch=52, velocity=0.7),  # third
    ]
    monkeypatch.setattr(pipeline_module, "extract_lh_notes", lambda audio_path: fake_notes)

    variants = _lh_variants("fake/harmony.wav")

    assert set(variants.keys()) == {"easy", "medium", "hard"}
    hard_count = len(list(variants["hard"].flatten().notes))
    easy_count = len(list(variants["easy"].flatten().notes))
    assert hard_count == 2  # Hard is the transcription itself, unmodified
    assert easy_count == 1  # Easy caps to a single voice (max_voices=1)


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
