import shutil
from pathlib import Path

SUPPORTED_EXTENSIONS = {".wav", ".mp3"}


class UnsupportedAudioFormat(Exception):
    pass


def save_uploaded_file(source_path: Path, dest_dir: Path, original_filename: str) -> Path:
    ext = Path(original_filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedAudioFormat(f"Unsupported file type: {ext}")

    dest_path = dest_dir / f"source{ext}"
    shutil.copy(source_path, dest_path)
    return dest_path
