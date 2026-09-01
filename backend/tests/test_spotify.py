import pytest
import spotipy

from app.ingestion import spotify as spotify_module
from app.ingestion.spotify import resolve_and_download, SpotifyResolutionError
from app.ingestion.youtube import YouTubeResolutionError


class _FakeSpotifyClient:
    def __init__(self, *, track_data=None, raise_error=False):
        self._track_data = track_data
        self._raise_error = raise_error

    def track(self, track_id):
        if self._raise_error:
            raise spotipy.SpotifyException(404, -1, "not found")
        return self._track_data


def test_resolve_and_download_happy_path(tmp_path, monkeypatch):
    fake_track = {"name": "Clair de Lune", "artists": [{"name": "Debussy"}]}
    monkeypatch.setattr(spotify_module, "SpotifyClientCredentials", lambda **kwargs: None)
    monkeypatch.setattr(
        spotify_module.spotipy, "Spotify",
        lambda auth_manager: _FakeSpotifyClient(track_data=fake_track),
    )
    monkeypatch.setattr(spotify_module, "_search_youtube", lambda query: "https://youtube.com/watch?v=xyz")
    monkeypatch.setattr(
        spotify_module, "download_audio",
        lambda url, dest_dir: (dest_dir / "source.mp3", "some youtube video title"),
    )

    path, title = resolve_and_download(
        "https://open.spotify.com/track/abc123", tmp_path, "id", "secret"
    )

    assert path == tmp_path / "source.mp3"
    # Uses the real Spotify track/artist metadata, not the YouTube video title.
    assert title == "Debussy - Clair de Lune"


def test_resolve_and_download_raises_on_unparseable_url(tmp_path):
    with pytest.raises(SpotifyResolutionError):
        resolve_and_download("https://open.spotify.com/album/notatrack", tmp_path, "id", "secret")


def test_resolve_and_download_raises_when_no_youtube_match(tmp_path, monkeypatch):
    fake_track = {"name": "Obscure Track", "artists": [{"name": "Nobody"}]}
    monkeypatch.setattr(spotify_module, "SpotifyClientCredentials", lambda **kwargs: None)
    monkeypatch.setattr(
        spotify_module.spotipy, "Spotify",
        lambda auth_manager: _FakeSpotifyClient(track_data=fake_track),
    )
    monkeypatch.setattr(spotify_module, "_search_youtube", lambda query: None)

    with pytest.raises(SpotifyResolutionError):
        resolve_and_download(
            "https://open.spotify.com/track/abc123", tmp_path, "id", "secret"
        )


def test_resolve_and_download_wraps_youtube_download_failure(tmp_path, monkeypatch):
    fake_track = {"name": "Clair de Lune", "artists": [{"name": "Debussy"}]}
    monkeypatch.setattr(spotify_module, "SpotifyClientCredentials", lambda **kwargs: None)
    monkeypatch.setattr(
        spotify_module.spotipy, "Spotify",
        lambda auth_manager: _FakeSpotifyClient(track_data=fake_track),
    )
    monkeypatch.setattr(spotify_module, "_search_youtube", lambda query: "https://youtube.com/watch?v=xyz")

    def failing_download(url, dest_dir):
        raise YouTubeResolutionError("download failed")

    monkeypatch.setattr(spotify_module, "download_audio", failing_download)

    with pytest.raises(SpotifyResolutionError):
        resolve_and_download(
            "https://open.spotify.com/track/abc123", tmp_path, "id", "secret"
        )
