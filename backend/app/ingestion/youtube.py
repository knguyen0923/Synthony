from pathlib import Path

import yt_dlp


class YouTubeResolutionError(Exception):
    pass


def download_audio(url: str, dest_dir: Path) -> Path:
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
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        raise YouTubeResolutionError(f"Could not download audio from {url}") from exc

    return dest_dir / "source.mp3"
