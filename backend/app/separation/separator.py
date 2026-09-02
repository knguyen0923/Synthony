import subprocess
import sys
from pathlib import Path

from app.separation.types import Stems

MODEL_NAME = "htdemucs"
STEM_NAMES = ("vocals", "drums", "bass", "other")


def separate_stems(audio_path: str, output_dir: Path) -> Stems:
    """Run Demucs 4-stem separation on audio_path, writing vocals/drums/
    bass/other WAV files under output_dir, and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [sys.executable, "-m", "demucs.separate", "-n", MODEL_NAME, "-o", str(output_dir), audio_path],
        check=True,
        capture_output=True,
    )

    track_name = Path(audio_path).stem
    stem_dir = output_dir / MODEL_NAME / track_name
    paths = {name: stem_dir / f"{name}.wav" for name in STEM_NAMES}
    return Stems(**paths)
