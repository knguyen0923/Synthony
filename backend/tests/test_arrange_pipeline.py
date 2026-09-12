import pytest
import numpy as np
from scipy.io import wavfile

from app.arrange_pipeline import _lh_variants, mix_wav_files, MIN_MELODY_NOTES, _is_instrumental
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


def test_is_instrumental_true_when_melody_notes_are_far_below_the_threshold():
    assert _is_instrumental([]) is True
    assert _is_instrumental([NoteEvent(start=0.0, end=0.5, pitch=60)]) is True


def test_is_instrumental_false_at_and_above_the_threshold():
    notes_at_threshold = [NoteEvent(start=float(i), end=float(i) + 0.5, pitch=60) for i in range(MIN_MELODY_NOTES)]
    assert _is_instrumental(notes_at_threshold) is False

    notes_above_threshold = notes_at_threshold + [NoteEvent(start=100.0, end=100.5, pitch=60)]
    assert _is_instrumental(notes_above_threshold) is False


def test_instrumental_variants_splits_notes_into_both_hands_via_dp(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    # A held low note plus a held high note at the same onset -- assign_hands'
    # DP splits a lone onset by pitch when there's no established continuity
    # yet, so this should land as one RH note and one LH note.
    fake_notes = [
        NoteEvent(start=0.0, end=2.0, pitch=72, velocity=0.8),  # high
        NoteEvent(start=0.0, end=2.0, pitch=48, velocity=0.8),  # low
    ]
    monkeypatch.setattr(pipeline_module, "transcribe_audio_to_notes", lambda audio_path, minimum_note_length=None: fake_notes)

    rh_variants, lh_variants = pipeline_module._instrumental_variants("fake/harmony.wav", 0.5)

    assert set(rh_variants.keys()) == {"easy", "medium", "hard"}
    assert set(lh_variants.keys()) == {"easy", "medium", "hard"}
    rh_pitches = [n.pitch.midi for n in rh_variants["hard"].flatten().notes]
    lh_pitches = [n.pitch.midi for n in lh_variants["hard"].flatten().notes]
    assert rh_pitches == [72]
    assert lh_pitches == [48]


def test_instrumental_variants_caps_simultaneous_voices_per_hand(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    # Five simultaneous high notes: assign_hands' hard span cutoff (2
    # octaves) and RH's melody tie-break will put some/all in RH; whichever
    # hand ends up with more than MAX_SIMULTANEOUS_VOICES_PER_HAND (4) must
    # get capped by cap_simultaneous_notes.
    fake_notes = [
        NoteEvent(start=0.0, end=2.0, pitch=pitch, velocity=velocity)
        for pitch, velocity in [(60, 0.9), (62, 0.8), (64, 0.7), (65, 0.6), (67, 0.1)]
    ]
    monkeypatch.setattr(pipeline_module, "transcribe_audio_to_notes", lambda audio_path, minimum_note_length=None: fake_notes)

    rh_variants, _lh_variants = pipeline_module._instrumental_variants("fake/harmony.wav", 0.5)

    hard_notes = list(rh_variants["hard"].flatten().notes)
    assert len(hard_notes) <= 4


def test_instrumental_variants_lh_stays_in_the_hard_lh_range(monkeypatch):
    import app.arrange_pipeline as pipeline_module
    from app.lh.extract import HARD_LH_RANGE

    fake_notes = [
        NoteEvent(start=0.0, end=1.0, pitch=90, velocity=0.9),  # high -- RH by span/tiebreak
        NoteEvent(start=0.0, end=1.0, pitch=84, velocity=0.5),  # also high, but should land LH and get shifted down
    ]
    monkeypatch.setattr(pipeline_module, "transcribe_audio_to_notes", lambda audio_path, minimum_note_length=None: fake_notes)

    _rh_variants, lh_variants = pipeline_module._instrumental_variants("fake/harmony.wav", 0.5)

    lh_pitches = [n.pitch.midi for n in lh_variants["hard"].flatten().notes]
    assert all(HARD_LH_RANGE[0] <= p <= HARD_LH_RANGE[1] for p in lh_pitches)


def test_instrumental_variants_passes_minimum_note_length_to_transcription(monkeypatch):
    import app.arrange_pipeline as pipeline_module
    from app.lh.extract import LH_MINIMUM_NOTE_LENGTH_MS

    captured = {}

    def fake_transcribe(audio_path, minimum_note_length=None):
        captured["minimum_note_length"] = minimum_note_length
        return [NoteEvent(start=0.0, end=1.0, pitch=60, velocity=0.5)]

    monkeypatch.setattr(pipeline_module, "transcribe_audio_to_notes", fake_transcribe)

    pipeline_module._instrumental_variants("fake/harmony.wav", 0.5)

    assert captured["minimum_note_length"] == LH_MINIMUM_NOTE_LENGTH_MS


def test_instrumental_variants_uses_a_beat_map_instead_of_a_fixed_tempo_when_given(monkeypatch):
    import app.arrange_pipeline as pipeline_module

    fake_notes = [NoteEvent(start=1.0, end=2.0, pitch=72, velocity=0.9)]
    monkeypatch.setattr(pipeline_module, "transcribe_audio_to_notes", lambda audio_path, minimum_note_length=None: fake_notes)

    beat_map = BeatMap([0.0, 1.0, 2.0])  # 60 BPM, unlike the 120 BPM default
    rh_variants, _lh_variants = pipeline_module._instrumental_variants("fake/harmony.wav", 0.5, beat_map=beat_map)

    rh_note = list(rh_variants["hard"].flatten().notes)[0]
    assert rh_note.offset == 1.0  # 1.0 QL, not the 2.0 QL a fixed 0.5s/quarter default would give
