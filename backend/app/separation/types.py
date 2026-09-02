from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Stems:
    vocals: Path
    drums: Path
    bass: Path
    other: Path
