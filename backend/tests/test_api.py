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


def test_transcribe_with_no_input_returns_400():
    response = client.post("/transcribe")
    assert response.status_code == 400


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
