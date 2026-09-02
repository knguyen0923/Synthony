import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.io import wavfile

from app.arrangement.engine import generate_lh_variants
from app.chords.detect import detect_chords
from app.export import export_musicxml
from app.jobs import set_failed, set_result, set_status
from app.melody.extract import extract_melody_notes, melody_part_for_tier
from app.notation.hand_split import build_grand_staff_score
from app.separation.separator import separate_stems
from app.storage import evict_oldest_songs, write_metadata

# Right-hand quantization grid per tier, in quarterLength units — mirrors
# the difficulty engine's philosophy (Spec 1's easy.py/medium.py narrow
# the RH; Spec 2 lacks that engine's grid input, so this narrows melody
# rhythm directly instead) so the right hand actually gets harder to play
# as the tier increases, instead of being identical across all three.
MELODY_GRID_BY_TIER = {"easy": 1.0, "medium": 0.5, "hard": 0.25}


def mix_wav_files(path_a: Path, path_b: Path, dest: Path) -> Path:
    """Sum two WAV files sample-for-sample into dest, normalizing to avoid
    clipping. Used to combine the bass+other stems into a single harmony
    signal for chord detection."""
    rate_a, audio_a = wavfile.read(str(path_a))
    _rate_b, audio_b = wavfile.read(str(path_b))

    n = min(len(audio_a), len(audio_b))
    mixed = audio_a[:n].astype(np.float64) + audio_b[:n].astype(np.float64)
    peak = np.max(np.abs(mixed))
    if peak > 0:
        mixed = mixed / peak * 32767

    wavfile.write(str(dest), rate_a, mixed.astype(np.int16))
    return dest


def run_arrange_pipeline(
    job_id: str,
    audio_path: str,
    title: str,
    source_type: str,
    source_url: Optional[str],
    song_id: str,
    dest_dir: Path,
) -> None:
    try:
        set_status(job_id, "separating")
        stems = separate_stems(audio_path, dest_dir / "stems")

        set_status(job_id, "extracting_melody")
        melody_notes = extract_melody_notes(str(stems.vocals))

        set_status(job_id, "detecting_chords")
        harmony_path = mix_wav_files(stems.bass, stems.other, dest_dir / "stems" / "harmony.wav")
        chords = detect_chords(str(harmony_path))
        if not chords:
            raise ValueError("No chords detected")

        set_status(job_id, "arranging")
        variants = generate_lh_variants(chords)

        difficulties = {}
        for tier, lh_part in (("easy", variants.easy), ("medium", variants.medium), ("hard", variants.hard)):
            rh_part = melody_part_for_tier(melody_notes, MELODY_GRID_BY_TIER[tier])
            score = build_grand_staff_score(rh_part, lh_part, title=title)
            export_musicxml(score, dest_dir / f"{tier}.musicxml")
            difficulties[tier] = {"musicxml_url": f"/storage/{song_id}/{tier}.musicxml"}

        write_metadata(song_id, title=title, source_type=source_type, source_url=source_url, pipeline="arrange")
        evict_oldest_songs()

        set_result(job_id, {"song_id": song_id, "title": title, "difficulties": difficulties})
    except Exception as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        set_failed(job_id, str(exc))
