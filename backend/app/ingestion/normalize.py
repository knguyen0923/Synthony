from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.ingestion.upload import save_uploaded_file, UnsupportedAudioFormat
from app.ingestion.youtube import download_audio, YouTubeResolutionError
from app.ingestion.spotify import resolve_and_download, SpotifyResolutionError


class IngestionError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class IngestedAudio:
    path: Path
    source_type: str
    source_url: Optional[str]


def ingest(
    dest_dir: Path,
    *,
    uploaded_file_path: Optional[Path] = None,
    uploaded_filename: Optional[str] = None,
    youtube_url: Optional[str] = None,
    spotify_url: Optional[str] = None,
    spotify_client_id: str = "",
    spotify_client_secret: str = "",
) -> IngestedAudio:
    if uploaded_file_path is not None:
        try:
            path = save_uploaded_file(uploaded_file_path, dest_dir, uploaded_filename or "")
        except UnsupportedAudioFormat as exc:
            raise IngestionError(str(exc), 400) from exc
        return IngestedAudio(path=path, source_type="upload", source_url=None)

    if youtube_url is not None:
        try:
            path = download_audio(youtube_url, dest_dir)
        except YouTubeResolutionError as exc:
            raise IngestionError(str(exc), 422) from exc
        return IngestedAudio(path=path, source_type="youtube", source_url=youtube_url)

    if spotify_url is not None:
        try:
            path = resolve_and_download(
                spotify_url, dest_dir, spotify_client_id, spotify_client_secret
            )
        except SpotifyResolutionError as exc:
            raise IngestionError(str(exc), 422) from exc
        return IngestedAudio(path=path, source_type="spotify", source_url=spotify_url)

    raise IngestionError("No input source provided", 400)
