import pytest
import spotipy
import yt_dlp

from app.ingestion import spotify as spotify_module
from app.ingestion.spotify import resolve_and_download, SpotifyResolutionError, SpotifyDurationExceededError
from app.ingestion.youtube import YouTubeResolutionError, YouTubeDurationExceededError


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
        lambda url, dest_dir, max_duration_seconds=None: (dest_dir / "source.mp3", "some youtube video title"),
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

    def failing_download(url, dest_dir, max_duration_seconds=None):
        raise YouTubeResolutionError("download failed")

    monkeypatch.setattr(spotify_module, "download_audio", failing_download)

    with pytest.raises(SpotifyResolutionError):
        resolve_and_download(
            "https://open.spotify.com/track/abc123", tmp_path, "id", "secret"
        )


def test_resolve_and_download_wraps_youtube_duration_exceeded(tmp_path, monkeypatch):
    fake_track = {"name": "Clair de Lune", "artists": [{"name": "Debussy"}]}
    monkeypatch.setattr(spotify_module, "SpotifyClientCredentials", lambda **kwargs: None)
    monkeypatch.setattr(
        spotify_module.spotipy, "Spotify",
        lambda auth_manager: _FakeSpotifyClient(track_data=fake_track),
    )
    monkeypatch.setattr(spotify_module, "_search_youtube", lambda query: "https://youtube.com/watch?v=xyz")

    def too_long_download(url, dest_dir, max_duration_seconds=None):
        raise YouTubeDurationExceededError("too long")

    monkeypatch.setattr(spotify_module, "download_audio", too_long_download)

    with pytest.raises(SpotifyDurationExceededError):
        resolve_and_download(
            "https://open.spotify.com/track/abc123", tmp_path, "id", "secret", max_duration_seconds=600
        )


def test_resolve_and_download_threads_max_duration_seconds_to_youtube(tmp_path, monkeypatch):
    fake_track = {"name": "Clair de Lune", "artists": [{"name": "Debussy"}]}
    monkeypatch.setattr(spotify_module, "SpotifyClientCredentials", lambda **kwargs: None)
    monkeypatch.setattr(
        spotify_module.spotipy, "Spotify",
        lambda auth_manager: _FakeSpotifyClient(track_data=fake_track),
    )
    monkeypatch.setattr(spotify_module, "_search_youtube", lambda query: "https://youtube.com/watch?v=xyz")

    captured = {}

    def fake_download(url, dest_dir, max_duration_seconds=None):
        captured["max_duration_seconds"] = max_duration_seconds
        return dest_dir / "source.mp3", "some youtube video title"

    monkeypatch.setattr(spotify_module, "download_audio", fake_download)

    resolve_and_download(
        "https://open.spotify.com/track/abc123", tmp_path, "id", "secret", max_duration_seconds=600
    )

    assert captured["max_duration_seconds"] == 600


def test_resolve_and_download_wraps_oauth_errors_as_resolution_errors(monkeypatch, tmp_path):
    """Confirmed by direct execution: SpotifyClientCredentials(...) raises
    SpotifyOauthError when client_id/client_secret are unset (the default,
    unconfigured state) -- SpotifyOauthError is NOT a subclass of
    spotipy.SpotifyException, so the pre-existing try/except (which only
    caught SpotifyException around client.track()) never caught it, and it
    propagated as a raw, unhandled exception."""
    def _raise_oauth_error(**kwargs):
        raise spotipy.oauth2.SpotifyOauthError("no client credentials set")

    monkeypatch.setattr(spotify_module, "SpotifyClientCredentials", _raise_oauth_error)

    with pytest.raises(SpotifyResolutionError):
        resolve_and_download(
            "https://open.spotify.com/track/abc123",
            tmp_path,
            "",
            "",
        )


def test_search_youtube_wraps_download_errors_as_resolution_errors(monkeypatch):
    """_search_youtube's yt_dlp.YoutubeDL(...).extract_info(...) call had no
    try/except anywhere in its call chain, unlike the structurally identical
    call in download_audio three lines below it."""
    from app.ingestion.spotify import _search_youtube

    class _FailingYoutubeDL:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, *args, **kwargs):
            raise spotify_module.yt_dlp.utils.DownloadError("network error")

    monkeypatch.setattr(spotify_module.yt_dlp, "YoutubeDL", _FailingYoutubeDL)

    with pytest.raises(SpotifyResolutionError):
        _search_youtube("some query")
