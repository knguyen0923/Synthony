import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

STORAGE_ROOT = Path(__file__).resolve().parent.parent / "storage"


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
