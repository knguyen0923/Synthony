from pathlib import Path
from typing import Tuple

import yt_dlp


class YouTubeResolutionError(Exception):
    pass


def download_audio(url: str, dest_dir: Path) -> Tuple[Path, str]:
    options = {
        "format": "bestaudio/best",
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
        }],
        "quiet": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise YouTubeResolutionError(f"Could not download audio from {url}") from exc

    title = (info or {}).get("title") or "Untitled"

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
