import re
from pathlib import Path
from typing import Optional, Tuple

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from app.ingestion.youtube import download_audio, YouTubeResolutionError

TRACK_ID_PATTERN = re.compile(r"track/([a-zA-Z0-9]+)")


class SpotifyResolutionError(Exception):
    pass


def resolve_and_download(
    spotify_url: str, dest_dir: Path, client_id: str, client_secret: str
) -> Tuple[Path, str]:
    match = TRACK_ID_PATTERN.search(spotify_url)
    if not match:
        raise SpotifyResolutionError(f"Could not parse Spotify track URL: {spotify_url}")
    track_id = match.group(1)

    auth_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    client = spotipy.Spotify(auth_manager=auth_manager)
    try:
        track = client.track(track_id)
    except spotipy.SpotifyException as exc:
        raise SpotifyResolutionError(f"Could not resolve Spotify track: {spotify_url}") from exc

    title = track["name"]
    artist = track["artists"][0]["name"]
    search_query = f"{title} {artist}"

    youtube_url = _search_youtube(search_query)
    if youtube_url is None:
        raise SpotifyResolutionError(f"No YouTube match found for '{search_query}'")

    try:
        path, _youtube_title = download_audio(youtube_url, dest_dir)
    except YouTubeResolutionError as exc:
        raise SpotifyResolutionError(str(exc)) from exc

    return path, f"{artist} - {title}"


def _search_youtube(query: str) -> Optional[str]:
    import yt_dlp

    options = {"quiet": True, "default_search": "ytsearch1", "noplaylist": True}
    with yt_dlp.YoutubeDL(options) as ydl:
        result = ydl.extract_info(query, download=False)
        entries = result.get("entries") or []
        if not entries:
            return None
        return entries[0]["webpage_url"]
