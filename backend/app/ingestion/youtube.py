from pathlib import Path
from typing import Optional, Tuple

import yt_dlp


class YouTubeResolutionError(Exception):
    pass


class YouTubeDurationExceededError(YouTubeResolutionError):
    pass


# Same rationale as the RH/LH client fallback below — a different official
# YouTube API client than the browser-facing default, not a bypass of any
# access restriction.
_EXTRACTOR_ARGS = {"youtube": {"player_client": ["android", "ios"]}}


def download_audio(
    url: str, dest_dir: Path, max_duration_seconds: Optional[int] = None
) -> Tuple[Path, str]:
    if max_duration_seconds is not None:
        _check_duration(url, max_duration_seconds)

    options = {
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
        }],
        "quiet": True,
        "noplaylist": True,
        # YouTube's "SABR streaming" restriction currently breaks direct-URL
        # extraction for the default web client on many videos (yt-dlp
        # issue #12482). Requesting formats via the android/ios API clients
        # instead avoids it — same public video, just a different official
        # client, not a DRM or access-restriction bypass.
        "extractor_args": _EXTRACTOR_ARGS,
    }
    title = "Untitled"
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
        title = (info or {}).get("title") or "Untitled"
    except yt_dlp.utils.DownloadError as exc:
        # The raw audio may have already downloaded successfully even though
        # this raised — yt-dlp wraps a postprocessing failure (e.g. ffmpeg
        # missing) as a DownloadError from extract_info() itself, not as a
        # silent no-op. Only treat this as a hard failure if nothing usable
        # actually landed on disk; otherwise use what's there (title is lost
        # since the info dict was never returned).
        candidates = sorted(dest_dir.glob("source.*"))
        if not candidates:
            raise YouTubeResolutionError(f"Could not download audio from {url}") from exc
        return candidates[0], title

    expected_path = dest_dir / "source.mp3"
    if expected_path.exists():
        return expected_path, title

    # ffmpeg wasn't available (or otherwise didn't run) so the postprocessor
    # never converted the raw download to source.mp3. Fall back to whatever
    # extension yt-dlp actually produced.
    candidates = sorted(dest_dir.glob("source.*"))
    if candidates:
        return candidates[0], title

    raise YouTubeResolutionError(
        "ffmpeg postprocessing did not produce the expected audio file — "
        "is ffmpeg installed?"
    )


def _check_duration(url: str, max_duration_seconds: int) -> None:
    """Reject an over-length video via a metadata-only lookup (no download),
    so a long video doesn't fully download before being rejected."""
    probe_options = {
        "quiet": True,
        "noplaylist": True,
        "extractor_args": _EXTRACTOR_ARGS,
    }
    try:
        with yt_dlp.YoutubeDL(probe_options) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise YouTubeResolutionError(f"Could not resolve audio from {url}") from exc

    duration = (info or {}).get("duration")
    if duration is not None and duration > max_duration_seconds:
        raise YouTubeDurationExceededError(
            f"Video exceeds the {max_duration_seconds // 60}-minute duration cap"
        )
