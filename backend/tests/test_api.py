import logging

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture
def _restore_root_logger_state():
    """Same purpose as test_logging_config.py's fixture of the same name:
    importlib.reload(main_module) (used by the startup-warning test below)
    re-runs configure_logging(), which calls
    logging.basicConfig(force=True) and permanently replaces the root
    logger's level and handlers for the rest of the pytest session
    otherwise."""
    root = logging.getLogger()
    original_level = root.level
    original_handlers = list(root.handlers)
    yield
    root.level = original_level
    root.handlers = original_handlers


def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_check_reports_ffmpeg_and_piano_model_status_when_both_present(monkeypatch):
    import shutil as shutil_module
    import app.main as main_module

    monkeypatch.setattr(shutil_module, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(main_module, "piano_checkpoint_downloaded", lambda: True)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ffmpeg_available": True,
        "piano_model_downloaded": True,
    }


def test_health_check_reports_missing_ffmpeg_and_undownloaded_model(monkeypatch):
    import shutil as shutil_module
    import app.main as main_module

    monkeypatch.setattr(shutil_module, "which", lambda name: None)
    monkeypatch.setattr(main_module, "piano_checkpoint_downloaded", lambda: False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ffmpeg_available": False,
        "piano_model_downloaded": False,
    }


def test_logs_a_warning_at_startup_when_ffmpeg_is_missing(monkeypatch, _restore_root_logger_state):
    import importlib
    import logging
    import shutil as shutil_module
    import app.main as main_module

    monkeypatch.setattr(shutil_module, "which", lambda name: None)

    records = []

    class _CollectingHandler(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _CollectingHandler()
    app_main_logger = logging.getLogger("app.main")
    app_main_logger.addHandler(handler)
    try:
        importlib.reload(main_module)
    finally:
        app_main_logger.removeHandler(handler)

    assert any("ffmpeg" in record.getMessage().lower() for record in records)


def test_transcribe_offloads_its_pipeline_so_other_requests_are_not_blocked(monkeypatch, synthetic_piano_wav):
    """Regression test for moving /transcribe's CPU-bound pipeline onto a
    worker thread via run_in_threadpool: before that fix, the whole
    single-threaded event loop was blocked for the pipeline's full
    duration, so even an unrelated /health request had to wait behind it.
    Uses its own TestClient, entered as a context manager, rather than
    this file's shared module-level `client` -- TestClient only keeps one
    persistent event-loop portal alive (shared across all requests made
    through it) when used as a context manager; the module-level `client`
    here is never entered that way, so each of its calls gets its own
    fresh, isolated portal and could never actually contend for one
    shared event loop the way two requests to a real running server
    would. This starts a slow /transcribe in a background thread and
    confirms /health -- issued through the SAME client instance -- still
    responds promptly while it's still "running" (the mocked
    transcription blocks on a threading.Event for up to 5s)."""
    import threading
    import time
    import app.main as main_module
    from app.transcription.audio_to_midi import PianoTranscriptionResult

    release = threading.Event()

    def _slow_then_empty(audio_path):
        release.wait(timeout=5.0)
        return PianoTranscriptionResult(notes=[], pedal_events=[])

    monkeypatch.setattr(main_module, "transcribe_piano_audio_to_notes", _slow_then_empty)

    with TestClient(app) as shared_client:
        def _make_slow_transcribe_request():
            with open(synthetic_piano_wav, "rb") as f:
                shared_client.post("/transcribe", files={"audio_file": ("slow.wav", f, "audio/wav")})

        thread = threading.Thread(target=_make_slow_transcribe_request)
        thread.start()
        time.sleep(0.3)  # let the request actually reach the mocked, blocking call

        start = time.monotonic()
        health_response = shared_client.get("/health")
        elapsed = time.monotonic() - start

        release.set()
        thread.join(timeout=5.0)

    assert health_response.status_code == 200
    assert elapsed < 1.0, f"/health took {elapsed:.2f}s -- /transcribe is still blocking the event loop"


from pathlib import Path

from app.storage import STORAGE_ROOT


def test_transcribe_with_file_upload_returns_all_three_difficulties(synthetic_piano_note_wav):
    with open(synthetic_piano_note_wav, "rb") as f:
        response = client.post(
            "/transcribe",
            files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
        )

    assert response.status_code == 200
    body = response.json()
    assert set(body["difficulties"].keys()) == {"easy", "medium", "hard"}

    song_id = body["song_id"]
    for tier in ("easy", "medium", "hard"):
        musicxml_path = STORAGE_ROOT / song_id / f"{tier}.musicxml"
        assert musicxml_path.exists()
        xml = musicxml_path.read_text()
        # Real title/part-name threading, not music21's defaults — a viewer
        # would otherwise show "Music21 Fragment" and an opaque hex id
        # instead of the song title and a blank staff. Part names are kept
        # (print-object="no") but not printed — a solo piano's two staves
        # don't need a label.
        assert f"<work-title>{body['title']}</work-title>" in xml
        assert "Music21 Fragment" not in xml
        assert '<part-name print-object="no">Right Hand</part-name>' in xml
        assert '<part-name print-object="no">Left Hand</part-name>' in xml


def test_transcribe_evicts_oldest_songs_once_over_the_history_cap(monkeypatch, synthetic_piano_note_wav):
    import app.storage as storage_module

    monkeypatch.setattr(storage_module, "MAX_STORED_SONGS", 2)

    song_ids = []
    for _ in range(3):
        with open(synthetic_piano_note_wav, "rb") as f:
            response = client.post(
                "/transcribe",
                files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
            )
        assert response.status_code == 200
        song_ids.append(response.json()["song_id"])

    # The first (oldest) song should have been evicted once the 3rd request
    # pushed the count over the cap; the 2 newest remain.
    assert not (STORAGE_ROOT / song_ids[0]).exists()
    assert (STORAGE_ROOT / song_ids[1]).exists()
    assert (STORAGE_ROOT / song_ids[2]).exists()


def test_transcribe_with_no_input_returns_400():
    response = client.post("/transcribe")
    assert response.status_code == 400


def test_transcribe_failure_cleans_up_orphan_song_dir(monkeypatch):
    """A request that fails after song_dir(song_id) has already created the
    directory (e.g. ingestion fails validation) must not leave an empty
    orphan directory behind under STORAGE_ROOT."""
    import app.main as main_module

    captured_song_ids = []
    real_new_song_id = main_module.new_song_id

    def spying_new_song_id():
        song_id = real_new_song_id()
        captured_song_ids.append(song_id)
        return song_id

    monkeypatch.setattr(main_module, "new_song_id", spying_new_song_id)

    response = client.post("/transcribe")

    assert response.status_code == 400
    assert captured_song_ids, "expected new_song_id() to have been called"
    for song_id in captured_song_ids:
        assert not (STORAGE_ROOT / song_id).exists()


def test_transcribe_no_pitched_content_cleans_up_orphan_song_dir(monkeypatch, synthetic_piano_wav):
    """A request that fails later in the pipeline (after real audio has been
    ingested into song_dir) must also clean up — not just early ingestion
    failures — including any audio file already written to disk."""
    import app.main as main_module

    from app.transcription.audio_to_midi import PianoTranscriptionResult

    monkeypatch.setattr(
        main_module,
        "transcribe_piano_audio_to_notes",
        lambda path: PianoTranscriptionResult(notes=[], pedal_events=[]),
    )

    captured_song_ids = []
    real_new_song_id = main_module.new_song_id

    def spying_new_song_id():
        song_id = real_new_song_id()
        captured_song_ids.append(song_id)
        return song_id

    monkeypatch.setattr(main_module, "new_song_id", spying_new_song_id)

    with open(synthetic_piano_wav, "rb") as f:
        response = client.post(
            "/transcribe",
            files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
        )

    assert response.status_code == 422
    assert captured_song_ids, "expected new_song_id() to have been called"
    for song_id in captured_song_ids:
        assert not (STORAGE_ROOT / song_id).exists()


import logging

import pytest


def test_transcribe_unexpected_failure_logs_the_exception(monkeypatch, caplog, synthetic_piano_wav):
    import app.main as main_module

    def boom(path):
        raise RuntimeError("model exploded")

    monkeypatch.setattr(main_module, "transcribe_piano_audio_to_notes", boom)

    with caplog.at_level(logging.ERROR, logger="app.main"):
        with open(synthetic_piano_wav, "rb") as f:
            with pytest.raises(RuntimeError, match="model exploded"):
                client.post(
                    "/transcribe",
                    files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
                )

    assert "transcribe failed" in caplog.text


def test_transcribe_expected_validation_failure_does_not_log_an_error(monkeypatch, caplog, synthetic_piano_wav):
    """A 422 "no pitched content" outcome is expected control flow, not a
    bug — it shouldn't produce an ERROR-level stack trace the way a genuine
    crash does."""
    import app.main as main_module
    from app.transcription.audio_to_midi import PianoTranscriptionResult

    monkeypatch.setattr(
        main_module,
        "transcribe_piano_audio_to_notes",
        lambda path: PianoTranscriptionResult(notes=[], pedal_events=[]),
    )

    with caplog.at_level(logging.ERROR, logger="app.main"):
        with open(synthetic_piano_wav, "rb") as f:
            response = client.post(
                "/transcribe",
                files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
            )

    assert response.status_code == 422
    assert "transcribe failed" not in caplog.text


def test_transcribe_returns_503_when_no_job_slot_available(monkeypatch, synthetic_piano_wav):
    import threading

    import app.concurrency as concurrency_module
    import app.main as main_module

    monkeypatch.setattr(concurrency_module, "_slots", threading.Semaphore(1))

    captured_song_ids = []
    real_new_song_id = main_module.new_song_id

    def spying_new_song_id():
        song_id = real_new_song_id()
        captured_song_ids.append(song_id)
        return song_id

    monkeypatch.setattr(main_module, "new_song_id", spying_new_song_id)

    with concurrency_module.job_slot():  # occupy the only slot
        with open(synthetic_piano_wav, "rb") as f:
            response = client.post(
                "/transcribe",
                files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
            )

    assert response.status_code == 503
    assert captured_song_ids, "expected new_song_id() to have been called"
    for song_id in captured_song_ids:
        assert not (STORAGE_ROOT / song_id).exists()


def test_cors_allows_frontend_dev_origin():
    # The frontend dev server runs on http://localhost:5173 and calls this
    # API cross-origin; the browser only exposes the response if the server
    # sends back a matching Access-Control-Allow-Origin header. FastAPI's
    # TestClient goes through the real middleware stack, so this exercises
    # actual CORS behavior, not just the presence of a middleware object.
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_preflight_for_transcribe_allows_frontend_dev_origin():
    response = client.options(
        "/transcribe",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_songs_lists_transcribed_songs_newest_first(synthetic_piano_note_wav):
    song_ids = []
    for _ in range(2):
        with open(synthetic_piano_note_wav, "rb") as f:
            response = client.post(
                "/transcribe",
                files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
            )
        song_ids.append(response.json()["song_id"])

    response = client.get("/songs")

    assert response.status_code == 200
    listed_ids = [s["song_id"] for s in response.json()]
    assert listed_ids == list(reversed(song_ids))


def test_get_song_returns_the_same_shape_as_transcribe(synthetic_piano_note_wav):
    with open(synthetic_piano_note_wav, "rb") as f:
        transcribe_response = client.post(
            "/transcribe",
            files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
        )
    song_id = transcribe_response.json()["song_id"]

    response = client.get(f"/songs/{song_id}")

    assert response.status_code == 200
    assert response.json() == transcribe_response.json()


def test_get_song_returns_404_for_unknown_id():
    response = client.get("/songs/does-not-exist")
    assert response.status_code == 404


def test_songs_listing_includes_pipeline_field(synthetic_piano_note_wav):
    with open(synthetic_piano_note_wav, "rb") as f:
        response = client.post(
            "/transcribe",
            files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
        )
    song_id = response.json()["song_id"]

    listing = client.get("/songs").json()
    entry = next(s for s in listing if s["song_id"] == song_id)
    assert entry["pipeline"] == "transcribe"


def test_delete_song_removes_it_from_storage_and_listing(synthetic_piano_note_wav):
    with open(synthetic_piano_note_wav, "rb") as f:
        transcribe_response = client.post(
            "/transcribe",
            files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
        )
    song_id = transcribe_response.json()["song_id"]

    delete_response = client.delete(f"/songs/{song_id}")

    assert delete_response.status_code == 204
    assert not (STORAGE_ROOT / song_id).exists()
    assert client.get(f"/songs/{song_id}").status_code == 404
    assert song_id not in [s["song_id"] for s in client.get("/songs").json()]


def test_delete_song_returns_404_for_unknown_id():
    response = client.delete("/songs/does-not-exist")
    assert response.status_code == 404


def test_transcribe_with_path_traversal_filename_stays_within_temp_dir(monkeypatch, synthetic_piano_note_wav):
    """A malicious filename like '../../../etc/passwant.wav' must not let the
    upload escape the request's temp directory. We monkeypatch
    tempfile.mkdtemp (which TemporaryDirectory uses under the hood) to learn
    the exact temp dir path the endpoint creates, then assert that no write
    ever lands outside of it — regardless of the attacker-supplied filename."""
    import tempfile as tempfile_module

    created_dirs = []
    real_mkdtemp = tempfile_module.mkdtemp

    def spying_mkdtemp(*args, **kwargs):
        d = real_mkdtemp(*args, **kwargs)
        created_dirs.append(Path(d))
        return d

    monkeypatch.setattr(tempfile_module, "mkdtemp", spying_mkdtemp)

    malicious_names = ["../../../etc/passwant.wav", "/etc/passwant.wav"]
    for name in malicious_names:
        with open(synthetic_piano_note_wav, "rb") as f:
            response = client.post(
                "/transcribe",
                files={"audio_file": (name, f, "audio/wav")},
            )
        # The sanitized filename becomes "passwant.wav" (or similar basename),
        # which is a supported extension, so ingestion proceeds normally
        # rather than escaping to /etc or a traversed path.
        assert response.status_code == 200

    assert created_dirs, "expected the endpoint to create at least one temp dir"
    for d in created_dirs:
        # The only files ever written under a request's temp dir must be
        # named by their sanitized basename, staying inside d — proving the
        # traversal/absolute-path components were stripped before any write.
        for f in d.rglob("*"):
            assert d in f.parents or f == d
    assert not Path("/etc/passwant.wav").exists()


import time

from music21 import note, stream

from app.notation.types import NoteEvent
from app.separation.types import Stems
from app.tempo.detect import BeatMap


def test_arrange_full_job_lifecycle_returns_transcribe_shaped_result(monkeypatch, synthetic_piano_wav):
    import app.arrange_pipeline as pipeline_module

    # 10 notes at 1s spacing -> span ~= 9s -> density ~= 1.1/s, safely above
    # MIN_MELODY_NOTE_DENSITY, so this exercises the normal (non-instrumental) path.
    fake_notes = [NoteEvent(start=float(i), end=float(i) + 0.5, pitch=72) for i in range(10)]
    fake_lh_notes = [NoteEvent(start=0.0, end=0.5, pitch=48)]

    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=Path("/fake/vocals.wav"), drums=Path("/fake/drums.wav"),
            bass=Path("/fake/bass.wav"), other=Path("/fake/other.wav"),
        ),
    )
    monkeypatch.setattr(pipeline_module, "mix_wav_files", lambda a, b, dest: dest)
    monkeypatch.setattr(pipeline_module, "extract_melody_notes", lambda audio_path: fake_notes)
    monkeypatch.setattr(pipeline_module, "extract_lh_notes", lambda audio_path: fake_lh_notes)
    monkeypatch.setattr(
        pipeline_module, "detect_key_and_tempo",
        lambda audio_path: ((0, "major"), 0.5),
    )
    monkeypatch.setattr(
        pipeline_module, "detect_beat_map",
        lambda audio_path: BeatMap.constant(0.5),
    )

    with open(synthetic_piano_wav, "rb") as f:
        response = client.post("/arrange", files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    job_id = body["job_id"]

    result = None
    for _ in range(50):
        payload = client.get(f"/arrange/{job_id}").json()
        if "song_id" in payload or payload.get("status") == "failed":
            result = payload
            break
        time.sleep(0.05)

    assert result is not None, "job did not complete in time"
    assert set(result["difficulties"].keys()) == {"easy", "medium", "hard"}
    song_id = result["song_id"]
    for tier in ("easy", "medium", "hard"):
        assert (STORAGE_ROOT / song_id / f"{tier}.musicxml").exists()


def test_arrange_routes_to_instrumental_path_when_no_real_melody_detected(monkeypatch, synthetic_piano_wav):
    import app.arrange_pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=Path("/fake/vocals.wav"), drums=Path("/fake/drums.wav"),
            bass=Path("/fake/bass.wav"), other=Path("/fake/other.wav"),
        ),
    )
    monkeypatch.setattr(pipeline_module, "mix_wav_files", lambda a, b, dest: dest)
    # Below MIN_MELODY_NOTES_FOR_DENSITY_CHECK -- must route to _instrumental_variants.
    monkeypatch.setattr(pipeline_module, "extract_melody_notes", lambda audio_path: [NoteEvent(start=0.0, end=0.5, pitch=60)])
    monkeypatch.setattr(pipeline_module, "detect_key_and_tempo", lambda audio_path: ((0, "major"), 0.5))
    monkeypatch.setattr(pipeline_module, "detect_beat_map", lambda audio_path: BeatMap.constant(0.5))

    instrumental_called = {}

    def fake_instrumental_variants(bass_path, other_path, seconds_per_quarter, beat_map=None):
        instrumental_called["called"] = True
        assert bass_path == "/fake/bass.wav"
        assert other_path == "/fake/other.wav"
        rh_part = stream.Part(id="RH")
        rh_part.insert(0.0, note.Note("C4"))
        lh_part = stream.Part(id="LH")
        lh_part.insert(0.0, note.Note("C3"))
        return (
            {"easy": rh_part, "medium": rh_part, "hard": rh_part},
            {"easy": lh_part, "medium": lh_part, "hard": lh_part},
        )

    monkeypatch.setattr(pipeline_module, "_instrumental_variants", fake_instrumental_variants)

    def boom_if_called(*args, **kwargs):
        raise AssertionError("_rh_variants/_lh_variants must not run on the instrumental path")

    monkeypatch.setattr(pipeline_module, "_rh_variants", boom_if_called)
    monkeypatch.setattr(pipeline_module, "_lh_variants", boom_if_called)

    with open(synthetic_piano_wav, "rb") as f:
        response = client.post("/arrange", files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")})
    job_id = response.json()["job_id"]

    result = None
    for _ in range(50):
        payload = client.get(f"/arrange/{job_id}").json()
        if "song_id" in payload or payload.get("status") == "failed":
            result = payload
            break
        time.sleep(0.05)

    assert result is not None, "job did not complete in time"
    assert instrumental_called.get("called") is True
    assert "song_id" in result, f"job failed instead of completing: {result}"


def test_arrange_does_not_route_to_instrumental_path_with_a_real_melody(monkeypatch, synthetic_piano_wav):
    import app.arrange_pipeline as pipeline_module

    monkeypatch.setattr(
        pipeline_module, "separate_stems",
        lambda audio_path, output_dir: Stems(
            vocals=Path("/fake/vocals.wav"), drums=Path("/fake/drums.wav"),
            bass=Path("/fake/bass.wav"), other=Path("/fake/other.wav"),
        ),
    )
    monkeypatch.setattr(pipeline_module, "mix_wav_files", lambda a, b, dest: dest)
    # 10 notes at 1s spacing -> span ~= 9s -> density ~= 1.1/s, safely above
    # MIN_MELODY_NOTE_DENSITY -- must stay on the existing path, unaffected.
    plenty_of_notes = [NoteEvent(start=float(i), end=float(i) + 0.5, pitch=72) for i in range(10)]
    monkeypatch.setattr(pipeline_module, "extract_melody_notes", lambda audio_path: plenty_of_notes)
    monkeypatch.setattr(pipeline_module, "extract_lh_notes", lambda audio_path: [NoteEvent(start=0.0, end=0.5, pitch=48)])
    monkeypatch.setattr(pipeline_module, "detect_key_and_tempo", lambda audio_path: ((0, "major"), 0.5))
    monkeypatch.setattr(pipeline_module, "detect_beat_map", lambda audio_path: BeatMap.constant(0.5))

    def boom_if_called(*args, **kwargs):
        raise AssertionError("_instrumental_variants must not run when a real melody was detected")

    monkeypatch.setattr(pipeline_module, "_instrumental_variants", boom_if_called)

    with open(synthetic_piano_wav, "rb") as f:
        response = client.post("/arrange", files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")})
    job_id = response.json()["job_id"]

    result = None
    for _ in range(50):
        payload = client.get(f"/arrange/{job_id}").json()
        if "song_id" in payload or payload.get("status") == "failed":
            result = payload
            break
        time.sleep(0.05)

    assert result is not None, "job did not complete in time"
    assert "song_id" in result, f"job failed instead of completing: {result}"


def test_arrange_job_failure_sets_failed_status_with_detail(monkeypatch, synthetic_piano_wav):
    import app.arrange_pipeline as pipeline_module

    def boom(audio_path, output_dir):
        raise RuntimeError("separation blew up")

    monkeypatch.setattr(pipeline_module, "separate_stems", boom)

    with open(synthetic_piano_wav, "rb") as f:
        response = client.post("/arrange", files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")})
    job_id = response.json()["job_id"]

    result = None
    for _ in range(50):
        payload = client.get(f"/arrange/{job_id}").json()
        if "song_id" in payload or payload.get("status") == "failed":
            result = payload
            break
        time.sleep(0.05)

    assert result == {"status": "failed", "detail": "Arrangement failed -- check the server logs for details"}
    assert not any(STORAGE_ROOT.iterdir())


def test_arrange_job_failure_logs_the_exception(monkeypatch, caplog, synthetic_piano_wav):
    import app.arrange_pipeline as pipeline_module

    def boom(audio_path, output_dir):
        raise RuntimeError("separation blew up")

    monkeypatch.setattr(pipeline_module, "separate_stems", boom)

    with caplog.at_level(logging.ERROR, logger="app.arrange_pipeline"):
        with open(synthetic_piano_wav, "rb") as f:
            response = client.post("/arrange", files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")})
        job_id = response.json()["job_id"]

        result = None
        for _ in range(50):
            payload = client.get(f"/arrange/{job_id}").json()
            if payload.get("status") == "failed":
                result = payload
                break
            time.sleep(0.05)

    assert result == {"status": "failed", "detail": "Arrangement failed -- check the server logs for details"}
    assert "arrange pipeline failed" in caplog.text


def test_arrange_status_returns_404_for_unknown_job():
    response = client.get("/arrange/does-not-exist")
    assert response.status_code == 404


def test_transcribe_rejects_non_audio_upload_with_a_clean_422():
    """Confirmed by direct execution: a text file renamed .mp3 passes
    upload.py's extension-only validation, then librosa.get_duration raises
    audioread.exceptions.NoBackendError -- previously uncaught (outside the
    try/except IngestionError block in _ingest_and_validate_duration),
    surfacing as a raw 500 instead of a clean 4xx."""
    response = client.post(
        "/transcribe",
        files={"audio_file": ("fake.mp3", b"this is not audio data, just text bytes", "audio/mpeg")},
    )
    assert response.status_code == 422
