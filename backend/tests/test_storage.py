import json
import uuid

from app.storage import (
    new_song_id,
    song_dir,
    write_metadata,
    evict_oldest_songs,
    STORAGE_ROOT,
)


def _make_song(title: str, created_at: str) -> str:
    """Create a song directory with an explicit created_at, so eviction
    ordering can be tested deterministically without sleeping in real time."""
    song_id = new_song_id()
    song_dir(song_id)
    write_metadata(song_id, title=title, source_type="upload", source_url=None)
    metadata_path = STORAGE_ROOT / song_id / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["created_at"] = created_at
    metadata_path.write_text(json.dumps(metadata))
    return song_id


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


def test_evict_oldest_songs_does_nothing_when_under_limit():
    ids = [_make_song(f"Song {i}", f"2026-01-0{i}T00:00:00+00:00") for i in range(1, 4)]

    evict_oldest_songs(limit=5)

    for song_id in ids:
        assert (STORAGE_ROOT / song_id).exists()


def test_evict_oldest_songs_removes_oldest_first_when_over_limit():
    oldest = _make_song("Oldest", "2026-01-01T00:00:00+00:00")
    middle = _make_song("Middle", "2026-01-02T00:00:00+00:00")
    newest = _make_song("Newest", "2026-01-03T00:00:00+00:00")

    evict_oldest_songs(limit=2)

    assert not (STORAGE_ROOT / oldest).exists()
    assert (STORAGE_ROOT / middle).exists()
    assert (STORAGE_ROOT / newest).exists()


def test_evict_oldest_songs_removes_exactly_enough_to_reach_the_limit():
    ids = [_make_song(f"Song {i}", f"2026-01-{i:02d}T00:00:00+00:00") for i in range(1, 8)]

    evict_oldest_songs(limit=5)

    remaining = [song_id for song_id in ids if (STORAGE_ROOT / song_id).exists()]
    assert len(remaining) == 5
    # The 2 oldest (Song 1, Song 2) should be the ones evicted.
    assert remaining == ids[2:]


def test_evict_oldest_songs_treats_a_directory_with_no_metadata_as_oldest():
    # A song directory with no metadata.json shouldn't happen in normal
    # operation (write_metadata always runs before a request succeeds), but
    # eviction must not crash on one — and it's junk, so evict it first.
    orphan_id = new_song_id()
    song_dir(orphan_id)

    normal_id = _make_song("Normal", "2026-01-01T00:00:00+00:00")

    evict_oldest_songs(limit=1)

    assert not (STORAGE_ROOT / orphan_id).exists()
    assert (STORAGE_ROOT / normal_id).exists()
