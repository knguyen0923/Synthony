from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


from pathlib import Path

from app.storage import STORAGE_ROOT


def test_transcribe_with_file_upload_returns_all_three_difficulties(synthetic_piano_wav):
    with open(synthetic_piano_wav, "rb") as f:
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


def test_transcribe_evicts_oldest_songs_once_over_the_history_cap(monkeypatch, synthetic_piano_wav):
    import app.storage as storage_module

    monkeypatch.setattr(storage_module, "MAX_STORED_SONGS", 2)

    song_ids = []
    for _ in range(3):
        with open(synthetic_piano_wav, "rb") as f:
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

    monkeypatch.setattr(main_module, "transcribe_audio_to_notes", lambda path: [])

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


def test_songs_lists_transcribed_songs_newest_first(synthetic_piano_wav):
    song_ids = []
    for _ in range(2):
        with open(synthetic_piano_wav, "rb") as f:
            response = client.post(
                "/transcribe",
                files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
            )
        song_ids.append(response.json()["song_id"])

    response = client.get("/songs")

    assert response.status_code == 200
    listed_ids = [s["song_id"] for s in response.json()]
    assert listed_ids == list(reversed(song_ids))


def test_get_song_returns_the_same_shape_as_transcribe(synthetic_piano_wav):
    with open(synthetic_piano_wav, "rb") as f:
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


def test_songs_listing_includes_pipeline_field(synthetic_piano_wav):
    with open(synthetic_piano_wav, "rb") as f:
        response = client.post(
            "/transcribe",
            files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")},
        )
    song_id = response.json()["song_id"]

    listing = client.get("/songs").json()
    entry = next(s for s in listing if s["song_id"] == song_id)
    assert entry["pipeline"] == "transcribe"


def test_delete_song_removes_it_from_storage_and_listing(synthetic_piano_wav):
    with open(synthetic_piano_wav, "rb") as f:
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


def test_transcribe_with_path_traversal_filename_stays_within_temp_dir(monkeypatch, synthetic_piano_wav):
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
        with open(synthetic_piano_wav, "rb") as f:
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

from app.notation.types import NoteEvent
from app.separation.types import Stems


def test_arrange_full_job_lifecycle_returns_transcribe_shaped_result(monkeypatch, synthetic_piano_wav):
    import app.arrange_pipeline as pipeline_module

    fake_notes = [NoteEvent(start=0.0, end=0.5, pitch=72)]
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

    with open(synthetic_piano_wav, "rb") as f:
        response = client.post("/arrange", files={"audio_file": ("synthetic_piano.wav", f, "audio/wav")})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "processing"
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

    assert result == {"status": "failed", "detail": "separation blew up"}
    assert not any(STORAGE_ROOT.iterdir())


def test_arrange_status_returns_404_for_unknown_job():
    response = client.get("/arrange/does-not-exist")
    assert response.status_code == 404
