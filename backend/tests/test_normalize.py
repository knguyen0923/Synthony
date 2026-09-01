import pytest

from app.ingestion import normalize as normalize_module
from app.ingestion.normalize import ingest, IngestionError
from app.ingestion.upload import UnsupportedAudioFormat
from app.ingestion.youtube import YouTubeResolutionError
from app.ingestion.spotify import SpotifyResolutionError


def test_ingest_dispatches_to_file_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(
        normalize_module, "save_uploaded_file",
        lambda source, dest_dir, filename: dest_dir / "source.wav",
    )

    result = ingest(tmp_path, uploaded_file_path=tmp_path / "in.wav", uploaded_filename="in.wav")

    assert result.source_type == "upload"
    assert result.source_url is None
    assert result.path == tmp_path / "source.wav"


def test_ingest_dispatches_to_youtube(tmp_path, monkeypatch):
    monkeypatch.setattr(
        normalize_module, "download_audio",
        lambda url, dest_dir: dest_dir / "source.mp3",
    )

    result = ingest(tmp_path, youtube_url="https://youtube.com/watch?v=abc")

    assert result.source_type == "youtube"
    assert result.source_url == "https://youtube.com/watch?v=abc"


def test_ingest_dispatches_to_spotify(tmp_path, monkeypatch):
    monkeypatch.setattr(
        normalize_module, "resolve_and_download",
        lambda url, dest_dir, client_id, client_secret: dest_dir / "source.mp3",
    )

    result = ingest(tmp_path, spotify_url="https://open.spotify.com/track/abc")

    assert result.source_type == "spotify"


def test_ingest_raises_400_when_no_input_provided(tmp_path):
    with pytest.raises(IngestionError) as exc_info:
        ingest(tmp_path)
    assert exc_info.value.status_code == 400


def test_ingest_wraps_unsupported_format_as_400(tmp_path, monkeypatch):
    def raise_unsupported(source, dest_dir, filename):
        raise UnsupportedAudioFormat("bad format")

    monkeypatch.setattr(normalize_module, "save_uploaded_file", raise_unsupported)

    with pytest.raises(IngestionError) as exc_info:
        ingest(tmp_path, uploaded_file_path=tmp_path / "in.flac", uploaded_filename="in.flac")
    assert exc_info.value.status_code == 400


def test_ingest_wraps_youtube_failure_as_422(tmp_path, monkeypatch):
    def raise_youtube_error(url, dest_dir):
        raise YouTubeResolutionError("unavailable")

    monkeypatch.setattr(normalize_module, "download_audio", raise_youtube_error)

    with pytest.raises(IngestionError) as exc_info:
        ingest(tmp_path, youtube_url="https://youtube.com/watch?v=broken")
    assert exc_info.value.status_code == 422


def test_ingest_wraps_spotify_failure_as_422(tmp_path, monkeypatch):
    def raise_spotify_error(url, dest_dir, client_id, client_secret):
        raise SpotifyResolutionError("no match")

    monkeypatch.setattr(normalize_module, "resolve_and_download", raise_spotify_error)

    with pytest.raises(IngestionError) as exc_info:
        ingest(tmp_path, spotify_url="https://open.spotify.com/track/abc")
    assert exc_info.value.status_code == 422
