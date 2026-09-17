import pytest
import numpy as np
from scipy.io import wavfile

from app.arrange_pipeline import _lh_variants, mix_wav_files, MIN_MELODY_NOTE_DENSITY, _is_instrumental
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

    # 10 notes at 1s spacing -> span ~= 9s -> density ~= 1.1/s, safely above
    # MIN_MELODY_NOTE_DENSITY, so this exercises the normal (non-instrumental) path.
    fake_notes = [NoteEvent(start=float(i), end=float(i) + 0.5, pitch=72) for i in range(10)]
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


def test_run_arrange_pipeline_fails_cleanly_when_slot_wait_times_out(tmp_path, monkeypatch):
    # If every slot stays busy long enough, a queued job must give up and
    # fail cleanly (set_failed) rather than block the calling thread
    # forever -- run_arrange_pipeline runs on Starlette's shared anyio
    # threadpool, so an unbounded wait here would eventually pin every
    # thread in that pool and starve the whole app.
    import app.arrange_pipeline as pipeline_module
    import app.concurrency as concurrency_module

    monkeypatch.setattr(concurrency_module, "_slots", threading.Semaphore(1))
    # JOB_QUEUE_TIMEOUT_SECONDS is read directly inside arrange_pipeline.py
    # (unlike _slots, which lives behind job_slot()'s own closure over
    # app.concurrency's globals), so patching it on pipeline_module does
    # take effect here.
    monkeypatch.setattr(pipeline_module, "JOB_QUEUE_TIMEOUT_SECONDS", 0.1)

    job_id = create_job()

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

    # Run synchronously -- the timeout (0.1s) means this returns quickly
    # once the slot wait gives up, rather than hanging.
    run_arrange_pipeline(
        job_id=job_id, audio_path="fake.wav", title="Song",
        source_type="upload", source_url=None, song_id="fake-song-id",
        dest_dir=tmp_path,
    )

    release_holder.set()
    holder_thread.join()

    job = get_job(job_id)
    assert job.status == "failed"
    assert "busy" in job.detail


def test_run_arrange_pipeline_deletes_the_stems_directory_after_success(tmp_path, monkeypatch):
    """Demucs's separated stem WAVs (and the mixed harmony.wav) are never
    read again once all three MusicXML tiers are exported -- they must
    not linger on disk forever. Real separate_stems() is mocked here (as
    in the job-slot tests above), so this test pre-creates a stems/
    directory with a dummy file to stand in for what the real call would
    have left behind, and asserts it's gone once the pipeline finishes
    successfully."""
    import app.arrange_pipeline as pipeline_module

    (tmp_path / "stems").mkdir()
    (tmp_path / "stems" / "vocals.wav").write_bytes(b"fake")

    fake_notes = [NoteEvent(start=float(i), end=float(i) + 0.5, pitch=72) for i in range(10)]
    fake_lh_notes = [NoteEvent(start=0.0, end=0.5, pitch=48)]
    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=tmp_path / "stems" / "vocals.wav", drums=tmp_path / "stems" / "drums.wav",
            bass=tmp_path / "stems" / "bass.wav", other=tmp_path / "stems" / "other.wav",
        ),
    )
    monkeypatch.setattr(pipeline_module, "mix_wav_files", lambda a, b, dest: dest)
    monkeypatch.setattr(pipeline_module, "extract_melody_notes", lambda audio_path: fake_notes)
    monkeypatch.setattr(pipeline_module, "extract_lh_notes", lambda audio_path: fake_lh_notes)
    monkeypatch.setattr(pipeline_module, "detect_key_and_tempo", lambda audio_path: ((0, "major"), 0.5))
    monkeypatch.setattr(pipeline_module, "detect_beat_map", lambda audio_path: BeatMap.constant(0.5))

    job_id = create_job()
    run_arrange_pipeline(
        job_id=job_id, audio_path="fake.wav", title="Song",
        source_type="upload", source_url=None, song_id="fake-song-id",
        dest_dir=tmp_path,
    )

    assert get_job(job_id).status == "done"
    assert not (tmp_path / "stems").exists()
    assert (tmp_path / "hard.musicxml").exists()


def _write_tone_wav(path, sample_rate=22050, duration=0.5, freq=220.0):
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    y = (0.5 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    wavfile.write(str(path), sample_rate, y)


def _write_silence_wav(path, sample_rate=22050, duration=0.5):
    y = np.zeros(int(sample_rate * duration), dtype=np.int16)
    wavfile.write(str(path), sample_rate, y)


def _setup_pipeline_common_mocks(pipeline_module, monkeypatch, stems):
    fake_notes = [NoteEvent(start=float(i), end=float(i) + 0.5, pitch=72) for i in range(10)]
    fake_lh_notes = [NoteEvent(start=0.0, end=0.5, pitch=48)]
    monkeypatch.setattr(pipeline_module, "separate_stems", lambda audio_path, output_dir: stems)
    monkeypatch.setattr(pipeline_module, "mix_wav_files", lambda a, b, dest: dest)
    monkeypatch.setattr(pipeline_module, "extract_melody_notes", lambda audio_path: fake_notes)
    monkeypatch.setattr(pipeline_module, "extract_lh_notes", lambda audio_path: fake_lh_notes)
    monkeypatch.setattr(pipeline_module, "detect_key_and_tempo", lambda audio_path: ((0, "major"), 0.5))


def test_run_arrange_pipeline_prefers_the_drums_stem_for_beat_detection_when_audible(tmp_path, monkeypatch):
    """The drums stem carries a far less ambiguous beat signal than the
    bass+other harmony mix (confirmed: madmom/librosa misread driving
    backbeat material as half-time on the harmony mix). When Demucs's
    drums stem has real signal, it must be what beat detection runs on."""
    import app.arrange_pipeline as pipeline_module

    (tmp_path / "stems").mkdir()
    drums_path = tmp_path / "stems" / "drums.wav"
    _write_tone_wav(drums_path)
    stems = Stems(
        vocals=tmp_path / "stems" / "vocals.wav", drums=drums_path,
        bass=tmp_path / "stems" / "bass.wav", other=tmp_path / "stems" / "other.wav",
    )
    _setup_pipeline_common_mocks(pipeline_module, monkeypatch, stems)

    calls = []
    monkeypatch.setattr(
        pipeline_module, "detect_beat_map",
        lambda audio_path: calls.append(audio_path) or BeatMap.constant(0.5),
    )

    job_id = create_job()
    run_arrange_pipeline(
        job_id=job_id, audio_path="fake.wav", title="Song",
        source_type="upload", source_url=None, song_id="fake-song-id",
        dest_dir=tmp_path,
    )

    assert get_job(job_id).status == "done"
    assert calls == [str(drums_path)]


def test_run_arrange_pipeline_falls_back_to_harmony_when_drums_stem_is_silent(tmp_path, monkeypatch):
    """A drums stem that's near-silent (e.g. a song with no percussion --
    Demucs still produces a drums.wav, just noise-floor/bleed-through)
    must not be trusted for beat detection; fall back to the existing
    bass+other harmony mix, matching pre-fix behavior."""
    import app.arrange_pipeline as pipeline_module

    (tmp_path / "stems").mkdir()
    drums_path = tmp_path / "stems" / "drums.wav"
    _write_silence_wav(drums_path)
    stems = Stems(
        vocals=tmp_path / "stems" / "vocals.wav", drums=drums_path,
        bass=tmp_path / "stems" / "bass.wav", other=tmp_path / "stems" / "other.wav",
    )
    _setup_pipeline_common_mocks(pipeline_module, monkeypatch, stems)

    calls = []
    monkeypatch.setattr(
        pipeline_module, "detect_beat_map",
        lambda audio_path: calls.append(audio_path) or BeatMap.constant(0.5),
    )

    job_id = create_job()
    run_arrange_pipeline(
        job_id=job_id, audio_path="fake.wav", title="Song",
        source_type="upload", source_url=None, song_id="fake-song-id",
        dest_dir=tmp_path,
    )

    assert get_job(job_id).status == "done"
    harmony_path = tmp_path / "stems" / "harmony.wav"
    assert calls == [str(harmony_path)]


def test_run_arrange_pipeline_deletes_the_whole_dest_dir_on_failure(tmp_path, monkeypatch):
    """Mirrors the success-path stems-cleanup test above: run_arrange_
    pipeline's except blocks already delete the ENTIRE dest_dir (not just
    stems/) on any failure -- this was previously unguarded by a test, so
    a future refactor could silently drop it without anything catching
    the regression."""
    import app.arrange_pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=tmp_path / "stems" / "vocals.wav", drums=tmp_path / "stems" / "drums.wav",
            bass=tmp_path / "stems" / "bass.wav", other=tmp_path / "stems" / "other.wav",
        ),
    )

    def _boom(audio_path):
        raise RuntimeError("simulated pipeline failure")

    monkeypatch.setattr(pipeline_module, "extract_melody_notes", _boom)

    job_id = create_job()
    run_arrange_pipeline(
        job_id=job_id, audio_path="fake.wav", title="Song",
        source_type="upload", source_url=None, song_id="fake-song-id",
        dest_dir=tmp_path,
    )

    assert get_job(job_id).status == "failed"
    assert get_job(job_id).detail == "Arrangement failed -- check the server logs for details"
    assert not tmp_path.exists()


def test_is_instrumental_true_when_below_the_note_count_floor():
    assert _is_instrumental([]) is True
    # 1 note -- below MIN_MELODY_NOTES_FOR_DENSITY_CHECK, can't compute density.
    assert _is_instrumental([NoteEvent(start=0.0, end=0.5, pitch=60)]) is True


def test_is_instrumental_true_when_note_density_is_low():
    # Mirrors the real instrumental measurement's shape: many notes, long
    # span, low rate. 10 notes 2s apart -- span ~= 18.3s, density ~= 0.55/s,
    # well below MIN_MELODY_NOTE_DENSITY (0.8).
    sparse_notes = [NoteEvent(start=float(i) * 2.0, end=float(i) * 2.0 + 0.3, pitch=60) for i in range(10)]
    assert _is_instrumental(sparse_notes) is True


def test_is_instrumental_false_when_note_density_is_high():
    # Mirrors a real-vocal-like rate: 10 notes 0.4s apart -- span ~= 3.9s,
    # density ~= 2.56/s, well above MIN_MELODY_NOTE_DENSITY (0.8).
    dense_notes = [NoteEvent(start=float(i) * 0.4, end=float(i) * 0.4 + 0.3, pitch=60) for i in range(10)]
    assert _is_instrumental(dense_notes) is False


def _fake_transcribe_by_path(bass_notes, other_notes):
    """Returns a fake transcribe_audio_to_notes that returns bass_notes for
    a path containing 'bass' and other_notes for a path containing 'other'
    -- matches how _instrumental_variants calls it once per stem path."""
    def fake(audio_path, minimum_note_length=None):
        if "bass" in audio_path:
            return bass_notes
        if "other" in audio_path:
            return other_notes
        raise AssertionError(f"unexpected audio_path: {audio_path}")
    return fake


def test_instrumental_variants_transcribes_bass_stem_to_lh_and_other_stem_to_rh(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    bass_notes = [NoteEvent(start=0.0, end=2.0, pitch=40, velocity=0.8)]
    other_notes = [NoteEvent(start=0.0, end=2.0, pitch=72, velocity=0.8)]
    monkeypatch.setattr(
        pipeline_module, "transcribe_audio_to_notes", _fake_transcribe_by_path(bass_notes, other_notes)
    )

    rh_variants, lh_variants = pipeline_module._instrumental_variants("fake/bass.wav", "fake/other.wav", 0.5)

    assert set(rh_variants.keys()) == {"easy", "medium", "hard"}
    assert set(lh_variants.keys()) == {"easy", "medium", "hard"}
    rh_pitches = [n.pitch.midi for n in rh_variants["hard"].flatten().notes]
    lh_pitches = [n.pitch.midi for n in lh_variants["hard"].flatten().notes]
    assert rh_pitches == [72]
    assert lh_pitches == [40]


def test_instrumental_variants_caps_simultaneous_voices_per_hand(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    # Five simultaneous notes from the "other" stem -- more than
    # MAX_SIMULTANEOUS_VOICES_PER_HAND (4) -- must get capped.
    other_notes = [
        NoteEvent(start=0.0, end=2.0, pitch=pitch, velocity=velocity)
        for pitch, velocity in [(60, 0.9), (62, 0.8), (64, 0.7), (65, 0.6), (67, 0.1)]
    ]
    monkeypatch.setattr(
        pipeline_module, "transcribe_audio_to_notes", _fake_transcribe_by_path([], other_notes)
    )

    rh_variants, _lh_variants = pipeline_module._instrumental_variants("fake/bass.wav", "fake/other.wav", 0.5)

    hard_notes = list(rh_variants["hard"].flatten().notes)
    assert len(hard_notes) <= 4


def test_instrumental_variants_lh_stays_in_the_hard_lh_range(monkeypatch):
    import app.arrange_pipeline as pipeline_module
    from app.lh.extract import HARD_LH_RANGE

    bass_notes = [
        NoteEvent(start=0.0, end=1.0, pitch=90, velocity=0.9),
        NoteEvent(start=0.0, end=1.0, pitch=84, velocity=0.5),
    ]
    monkeypatch.setattr(
        pipeline_module, "transcribe_audio_to_notes", _fake_transcribe_by_path(bass_notes, [])
    )

    _rh_variants, lh_variants = pipeline_module._instrumental_variants("fake/bass.wav", "fake/other.wav", 0.5)

    lh_pitches = [n.pitch.midi for n in lh_variants["hard"].flatten().notes]
    assert all(HARD_LH_RANGE[0] <= p <= HARD_LH_RANGE[1] for p in lh_pitches)


def test_instrumental_variants_passes_minimum_note_length_to_both_transcriptions(monkeypatch):
    import app.arrange_pipeline as pipeline_module
    from app.lh.extract import LH_MINIMUM_NOTE_LENGTH_MS

    captured = []

    def fake_transcribe(audio_path, minimum_note_length=None):
        captured.append((audio_path, minimum_note_length))
        return [NoteEvent(start=0.0, end=1.0, pitch=60, velocity=0.5)]

    monkeypatch.setattr(pipeline_module, "transcribe_audio_to_notes", fake_transcribe)

    pipeline_module._instrumental_variants("fake/bass.wav", "fake/other.wav", 0.5)

    assert len(captured) == 2
    assert all(minimum_note_length == LH_MINIMUM_NOTE_LENGTH_MS for _path, minimum_note_length in captured)
    assert {path for path, _ in captured} == {"fake/bass.wav", "fake/other.wav"}


def test_instrumental_variants_uses_a_beat_map_instead_of_a_fixed_tempo_when_given(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    other_notes = [NoteEvent(start=1.0, end=2.0, pitch=72, velocity=0.9)]
    monkeypatch.setattr(
        pipeline_module, "transcribe_audio_to_notes", _fake_transcribe_by_path([], other_notes)
    )

    beat_map = BeatMap([0.0, 1.0, 2.0])  # 60 BPM, unlike the 120 BPM default
    rh_variants, _lh_variants = pipeline_module._instrumental_variants(
        "fake/bass.wav", "fake/other.wav", 0.5, beat_map=beat_map
    )

    rh_note = list(rh_variants["hard"].flatten().notes)[0]
    assert rh_note.offset == 1.0  # 1.0 QL, not the 2.0 QL a fixed 0.5s/quarter default would give


def test_instrumental_variants_easy_medium_use_the_same_grids_ranges_and_voice_caps_as_the_normal_path(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    rh_chord = [
        NoteEvent(start=0.0, end=2.0, pitch=60, velocity=0.5),
        NoteEvent(start=0.0, end=2.0, pitch=64, velocity=0.7),
        NoteEvent(start=0.0, end=2.0, pitch=67, velocity=0.6),
        NoteEvent(start=0.0, end=2.0, pitch=72, velocity=0.95),
    ]
    lh_chord = [
        NoteEvent(start=0.0, end=2.0, pitch=36, velocity=0.5),
        NoteEvent(start=0.0, end=2.0, pitch=40, velocity=0.7),
        NoteEvent(start=0.0, end=2.0, pitch=43, velocity=0.6),
    ]
    monkeypatch.setattr(
        pipeline_module, "transcribe_audio_to_notes", _fake_transcribe_by_path(lh_chord, rh_chord)
    )

    rh_variants, lh_variants = pipeline_module._instrumental_variants("fake/bass.wav", "fake/other.wav", 0.5)

    # RH Easy: exactly 1 voice (the highest-velocity note), within EASY_RH_RANGE.
    rh_easy_notes = list(rh_variants["easy"].flatten().notes)
    assert len(rh_easy_notes) == 1
    assert all(
        pipeline_module.EASY_RH_RANGE[0] <= n.pitch.midi <= pipeline_module.EASY_RH_RANGE[1]
        for n in rh_easy_notes
    )

    # RH Medium: at most MAX_VOICING_TONES voices, more than 1, within MEDIUM_RH_RANGE.
    rh_medium_notes = list(rh_variants["medium"].flatten().notes)
    assert 1 < len(rh_medium_notes) <= pipeline_module.MAX_VOICING_TONES
    assert all(
        pipeline_module.MEDIUM_RH_RANGE[0] <= n.pitch.midi <= pipeline_module.MEDIUM_RH_RANGE[1]
        for n in rh_medium_notes
    )

    # LH Easy/Medium: same grids/ranges/voice caps _lh_variants already uses.
    lh_easy_notes = list(lh_variants["easy"].flatten().notes)
    assert len(lh_easy_notes) == 1
    assert all(
        pipeline_module.EASY_LH_RANGE[0] <= n.pitch.midi <= pipeline_module.EASY_LH_RANGE[1]
        for n in lh_easy_notes
    )

    lh_medium_notes = list(lh_variants["medium"].flatten().notes)
    assert len(lh_medium_notes) <= pipeline_module.MAX_VOICING_TONES
    assert all(
        pipeline_module.MEDIUM_LH_RANGE[0] <= n.pitch.midi <= pipeline_module.MEDIUM_LH_RANGE[1]
        for n in lh_medium_notes
    )


def test_instrumental_variants_raises_when_no_harmonic_content_detected(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "transcribe_audio_to_notes", _fake_transcribe_by_path([], []))

    with pytest.raises(ValueError, match="No harmonic content detected"):
        pipeline_module._instrumental_variants("fake/bass.wav", "fake/other.wav", 0.5)


def test_instrumental_variants_logs_a_warning_when_one_hand_is_empty(monkeypatch, caplog):
    import logging
    import app.arrange_pipeline as pipeline_module

    other_notes = [NoteEvent(start=0.0, end=1.0, pitch=60, velocity=0.5)]
    monkeypatch.setattr(
        pipeline_module, "transcribe_audio_to_notes", _fake_transcribe_by_path([], other_notes)
    )

    with caplog.at_level(logging.WARNING, logger="app.arrange_pipeline"):
        pipeline_module._instrumental_variants("fake/bass.wav", "fake/other.wav", 0.5)

    assert any("bass" in record.message.lower() and "empty" in record.message.lower() for record in caplog.records)
