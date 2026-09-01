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
