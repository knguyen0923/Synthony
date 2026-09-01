import json
import uuid

from app.storage import new_song_id, song_dir, write_metadata, STORAGE_ROOT


def test_new_song_id_is_a_valid_uuid4():
    song_id = new_song_id()
    assert uuid.UUID(song_id).version == 4


def test_song_dir_creates_and_returns_the_directory():
    song_id = new_song_id()
    path = song_dir(song_id)
    assert path == STORAGE_ROOT / song_id
    assert path.is_dir()


def test_write_metadata_writes_expected_json_fields():
    song_id = new_song_id()
    song_dir(song_id)

    write_metadata(song_id, title="My Song", source_type="upload", source_url=None)

    metadata_path = STORAGE_ROOT / song_id / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    assert metadata["title"] == "My Song"
    assert metadata["source_type"] == "upload"
    assert metadata["source_url"] is None
    assert "created_at" in metadata
