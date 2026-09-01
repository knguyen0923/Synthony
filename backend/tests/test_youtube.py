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

    def extract_info(self, url, download=True):
        self.downloaded_url = url
        # Simulate ffmpeg postprocessing actually producing source.mp3.
        dest_dir = self._dest_dir_from_outtmpl()
        (dest_dir / "source.mp3").write_bytes(b"fake mp3 bytes")
        return {"title": "Clair de Lune (Debussy)"}

    def _dest_dir_from_outtmpl(self):
        from pathlib import Path

        return Path(self.options["outtmpl"]).parent


def test_download_audio_calls_yt_dlp_and_returns_expected_path_and_title(tmp_path, monkeypatch):
    captured = {}

    def fake_youtube_dl(options):
        captured["options"] = options
        return _FakeYoutubeDL(options)

    monkeypatch.setattr(yt_dlp, "YoutubeDL", fake_youtube_dl)

    path, title = download_audio("https://youtube.com/watch?v=abc123", tmp_path)

    assert path == tmp_path / "source.mp3"
    assert title == "Clair de Lune (Debussy)"
    assert captured["options"]["outtmpl"] == str(tmp_path / "source.%(ext)s")


def test_download_audio_wraps_download_errors(tmp_path, monkeypatch):
    class _FailingYoutubeDL(_FakeYoutubeDL):
        def extract_info(self, url, download=True):
            raise yt_dlp.utils.DownloadError("video unavailable")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", lambda options: _FailingYoutubeDL(options))

    with pytest.raises(YouTubeResolutionError):
        download_audio("https://youtube.com/watch?v=broken", tmp_path)


def test_download_audio_falls_back_to_actual_extension_when_mp3_missing(tmp_path, monkeypatch):
    """Simulates ffmpeg not being installed: yt-dlp "succeeds" but the
    FFmpegExtractAudio postprocessor never runs, so no source.mp3 is
    produced — only the raw download (e.g. source.webm) exists."""

    class _NoFfmpegYoutubeDL(_FakeYoutubeDL):
        def extract_info(self, url, download=True):
            self.downloaded_url = url
            dest_dir = self._dest_dir_from_outtmpl()
            (dest_dir / "source.webm").write_bytes(b"raw webm bytes")
            return {"title": "Some Video"}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", lambda options: _NoFfmpegYoutubeDL(options))

    path, title = download_audio("https://youtube.com/watch?v=noffmpeg", tmp_path)

    assert path == tmp_path / "source.webm"
    assert title == "Some Video"


def test_download_audio_raises_clean_error_when_no_file_produced_at_all(tmp_path, monkeypatch):
    class _NoOutputYoutubeDL(_FakeYoutubeDL):
        def extract_info(self, url, download=True):
            self.downloaded_url = url
            return {"title": "Ghost Video"}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", lambda options: _NoOutputYoutubeDL(options))

    with pytest.raises(YouTubeResolutionError, match="ffmpeg"):
        download_audio("https://youtube.com/watch?v=noaudio", tmp_path)
