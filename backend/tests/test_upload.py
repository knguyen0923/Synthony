import pytest

from app.ingestion.upload import save_uploaded_file, UnsupportedAudioFormat


def test_save_uploaded_file_copies_wav_to_dest_dir(tmp_path):
    source = tmp_path / "input.wav"
    source.write_bytes(b"fake wav bytes")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    result = save_uploaded_file(source, dest_dir, "input.wav")

    assert result == dest_dir / "source.wav"
    assert result.read_bytes() == b"fake wav bytes"


def test_save_uploaded_file_rejects_unsupported_extension(tmp_path):
    source = tmp_path / "input.flac"
    source.write_bytes(b"fake flac bytes")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    with pytest.raises(UnsupportedAudioFormat):
        save_uploaded_file(source, dest_dir, "input.flac")
