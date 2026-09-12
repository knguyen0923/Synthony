import pytest
import numpy as np
from scipy.io import wavfile

from app.arrange_pipeline import _lh_variants, mix_wav_files
from app.notation.types import NoteEvent
from app.tempo.detect import BeatMap


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


def test_lh_variants_uses_a_beat_map_instead_of_a_fixed_tempo_when_given(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    fake_notes = [NoteEvent(start=1.0, end=2.0, pitch=48)]
    monkeypatch.setattr(pipeline_module, "extract_lh_notes", lambda audio_path: fake_notes)

    beat_map = BeatMap([0.0, 1.0, 2.0])  # 60 BPM, unlike the 120 BPM default
    variants = _lh_variants("fake/harmony.wav", beat_map=beat_map)

    hard_note = list(variants["hard"].flatten().notes)[0]
    assert hard_note.offset == 1.0  # 1.0 QL, not the 2.0 QL a 120 BPM default would give


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


import threading
import time

from app.arrange_pipeline import run_arrange_pipeline
from app.jobs import create_job, get_job
from app.separation.types import Stems


def test_run_arrange_pipeline_waits_for_a_job_slot(tmp_path, monkeypatch):
    import app.arrange_pipeline as pipeline_module
    import app.concurrency as concurrency_module

    # job_slot() (used both by run_arrange_pipeline, via its `from
    # app.concurrency import job_slot`, and by the holder thread below) is
    # a plain function whose closure always resolves `_slots` against
    # app.concurrency's own module globals -- monkeypatching
    # pipeline_module._slots would not exist (arrange_pipeline.py never
    # binds that name) and, even if it did, wouldn't affect the semaphore
    # job_slot() actually acquires. Patch the real one.
    monkeypatch.setattr(concurrency_module, "_slots", threading.Semaphore(1))

    fake_notes = [NoteEvent(start=0.0, end=0.5, pitch=72)]
    fake_lh_notes = [NoteEvent(start=0.0, end=0.5, pitch=48)]
    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=tmp_path / "vocals.wav", drums=tmp_path / "drums.wav",
            bass=tmp_path / "bass.wav", other=tmp_path / "other.wav",
        ),
    )
    monkeypatch.setattr(pipeline_module, "mix_wav_files", lambda a, b, dest: dest)
    monkeypatch.setattr(pipeline_module, "extract_melody_notes", lambda audio_path: fake_notes)
    monkeypatch.setattr(pipeline_module, "extract_lh_notes", lambda audio_path: fake_lh_notes)
    monkeypatch.setattr(pipeline_module, "detect_key_and_tempo", lambda audio_path: ((0, "major"), 0.5))
    monkeypatch.setattr(pipeline_module, "detect_beat_map", lambda audio_path: BeatMap.constant(0.5))

    job_id = create_job()
    assert get_job(job_id).status == "queued"

    # Occupy the only slot from this thread so the pipeline (run in its own
    # thread below) has to actually wait for it.
    from app.concurrency import job_slot as real_job_slot

    holding = threading.Event()
    release_holder = threading.Event()

    def hold_slot():
        with real_job_slot():
            holding.set()
            release_holder.wait(timeout=2.0)

    holder_thread = threading.Thread(target=hold_slot)
    holder_thread.start()
    holding.wait(timeout=1.0)

    pipeline_thread = threading.Thread(
        target=run_arrange_pipeline,
        kwargs=dict(
            job_id=job_id, audio_path="fake.wav", title="Song",
            source_type="upload", source_url=None, song_id="fake-song-id",
            dest_dir=tmp_path,
        ),
    )
    pipeline_thread.start()

    time.sleep(0.1)
    assert get_job(job_id).status == "queued"  # still waiting on the held slot

    release_holder.set()
    holder_thread.join()
    pipeline_thread.join(timeout=5.0)

    assert get_job(job_id).status == "done"
