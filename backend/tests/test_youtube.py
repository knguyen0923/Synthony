import pytest
import yt_dlp

from app.ingestion.youtube import download_audio, YouTubeResolutionError, YouTubeDurationExceededError


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


def test_download_audio_falls_back_to_raw_file_when_postprocessing_raises_download_error(
    tmp_path, monkeypatch
):
    """Real-world case (confirmed against a live video): the raw audio
    download succeeds and lands on disk, but yt-dlp's FFmpegExtractAudio
    postprocessor then fails (e.g. ffmpeg is missing) — yt-dlp wraps that
    failure as a DownloadError raised from extract_info() itself, not as a
    silent no-op. The already-downloaded file must still be used rather
    than discarded as if the download itself had failed."""

    class _PostprocessingFailsYoutubeDL(_FakeYoutubeDL):
        def extract_info(self, url, download=True):
            self.downloaded_url = url
            dest_dir = self._dest_dir_from_outtmpl()
            (dest_dir / "source.mp4").write_bytes(b"raw mp4 bytes, download succeeded")
            raise yt_dlp.utils.DownloadError(
                "ERROR: Postprocessing: ffprobe and ffmpeg not found."
            )

    monkeypatch.setattr(yt_dlp, "YoutubeDL", lambda options: _PostprocessingFailsYoutubeDL(options))

    path, title = download_audio("https://youtube.com/watch?v=ppfail", tmp_path)

    assert path == tmp_path / "source.mp4"
    assert title == "Untitled"


def test_download_audio_raises_clean_error_when_no_file_produced_at_all(tmp_path, monkeypatch):
    class _NoOutputYoutubeDL(_FakeYoutubeDL):
        def extract_info(self, url, download=True):
            self.downloaded_url = url
            return {"title": "Ghost Video"}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", lambda options: _NoOutputYoutubeDL(options))

    with pytest.raises(YouTubeResolutionError, match="ffmpeg"):
        download_audio("https://youtube.com/watch?v=noaudio", tmp_path)


def test_download_audio_rejects_over_length_video_without_downloading(tmp_path, monkeypatch):
    """A video over the duration cap must be rejected via a metadata-only
    probe (download=False) — never actually downloaded."""

    class _LongVideoYoutubeDL(_FakeYoutubeDL):
        def extract_info(self, url, download=True):
            assert not download, "must only probe metadata, never download, once over the cap"
            return {"duration": 700}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", lambda options: _LongVideoYoutubeDL(options))

    with pytest.raises(YouTubeDurationExceededError):
        download_audio("https://youtube.com/watch?v=toolong", tmp_path, max_duration_seconds=600)

    assert list(tmp_path.iterdir()) == []


def test_download_audio_proceeds_when_under_duration_cap(tmp_path, monkeypatch):
    class _ShortVideoYoutubeDL(_FakeYoutubeDL):
        def extract_info(self, url, download=True):
            if not download:
                return {"duration": 120}
            return super().extract_info(url, download=download)

    monkeypatch.setattr(yt_dlp, "YoutubeDL", lambda options: _ShortVideoYoutubeDL(options))

    path, title = download_audio(
        "https://youtube.com/watch?v=short", tmp_path, max_duration_seconds=600
    )

    assert path == tmp_path / "source.mp3"
    assert title == "Clair de Lune (Debussy)"


def test_download_audio_skips_duration_check_when_not_requested(tmp_path, monkeypatch):
    """No max_duration_seconds -> no metadata-only probe call at all."""
    download_calls = []

    class _TrackingYoutubeDL(_FakeYoutubeDL):
        def extract_info(self, url, download=True):
            download_calls.append(download)
            return super().extract_info(url, download=download)

    monkeypatch.setattr(yt_dlp, "YoutubeDL", lambda options: _TrackingYoutubeDL(options))

    download_audio("https://youtube.com/watch?v=abc123", tmp_path)

    assert download_calls == [True]
