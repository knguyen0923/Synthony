import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

STORAGE_ROOT = Path(__file__).resolve().parent.parent / "storage"

# Personal-use history cap: song directories are 3-8MB each (mostly the
# source-audio copy, MusicXML output is tiny), so this is a soft convenience
# limit rather than a response to any real disk-space pressure.
MAX_STORED_SONGS = 100


def new_song_id() -> str:
    return str(uuid.uuid4())


def song_dir(song_id: str) -> Path:
    path = STORAGE_ROOT / song_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_metadata(song_id: str, title: str, source_type: str, source_url: Optional[str]) -> None:
    metadata = {
        "title": title,
        "source_type": source_type,
        "source_url": source_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (song_dir(song_id) / "metadata.json").write_text(json.dumps(metadata, indent=2))


def _created_at_sort_key(path: Path) -> str:
    metadata_path = path / "metadata.json"
    if metadata_path.exists():
        try:
            return json.loads(metadata_path.read_text())["created_at"]
        except (json.JSONDecodeError, KeyError):
            pass
    # No/invalid metadata shouldn't happen in normal operation, but if it
    # does, it's junk — sort it first so it's evicted before any real song.
    return ""


def evict_oldest_songs(limit: Optional[int] = None) -> None:
    """Keep at most `limit` song directories (default MAX_STORED_SONGS, read
    at call time so tests can monkeypatch it), deleting the oldest ones (by
    metadata.json's created_at) first once that's exceeded."""
    if limit is None:
        limit = MAX_STORED_SONGS
    if not STORAGE_ROOT.exists():
        return

    song_dirs = [d for d in STORAGE_ROOT.iterdir() if d.is_dir()]
    excess = len(song_dirs) - limit
    if excess <= 0:
        return

    song_dirs.sort(key=_created_at_sort_key)
    for d in song_dirs[:excess]:
        delete_song(d.name)


def read_song(song_id: str) -> Optional[dict]:
    """Read a stored song's metadata by id, or None if it doesn't exist
    (e.g. it was never created, or was since deleted/evicted)."""
    metadata_path = STORAGE_ROOT / song_id / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text())
    except json.JSONDecodeError:
        return None
    return {"song_id": song_id, **metadata}


def list_songs() -> list[dict]:
    """List every stored song's metadata, newest first."""
    if not STORAGE_ROOT.exists():
        return []

    songs = [read_song(d.name) for d in STORAGE_ROOT.iterdir() if d.is_dir()]
    songs = [s for s in songs if s is not None]
    songs.sort(key=lambda s: s["created_at"], reverse=True)
    return songs


def delete_song(song_id: str) -> None:
    shutil.rmtree(STORAGE_ROOT / song_id, ignore_errors=True)
