import pytest
import yt_dlp

from app.ingestion.youtube import download_audio, YouTubeResolutionError


class _FakeYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def download(self, urls):
        self.downloaded_urls = urls


def test_download_audio_calls_yt_dlp_and_returns_expected_path(tmp_path, monkeypatch):
    captured = {}

    def fake_youtube_dl(options):
        captured["options"] = options
        return _FakeYoutubeDL(options)

    monkeypatch.setattr(yt_dlp, "YoutubeDL", fake_youtube_dl)

    result = download_audio("https://youtube.com/watch?v=abc123", tmp_path)

    assert result == tmp_path / "source.mp3"
    assert captured["options"]["outtmpl"] == str(tmp_path / "source.%(ext)s")


def test_download_audio_wraps_download_errors(tmp_path, monkeypatch):
    class _FailingYoutubeDL(_FakeYoutubeDL):
        def download(self, urls):
            raise yt_dlp.utils.DownloadError("video unavailable")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", lambda options: _FailingYoutubeDL(options))

    with pytest.raises(YouTubeResolutionError):
        download_audio("https://youtube.com/watch?v=broken", tmp_path)
