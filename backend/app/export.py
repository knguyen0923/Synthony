from pathlib import Path

from music21 import stream


def export_musicxml(score: stream.Score, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    score.write("musicxml", fp=str(output_path))
    return output_path
