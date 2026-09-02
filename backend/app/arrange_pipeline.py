import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.io import wavfile

from app.arrangement.engine import generate_lh_variants
from app.chords.detect import detect_chords
from app.difficulty.easy import EASY_GRID, EASY_RH_RANGE
from app.difficulty.medium import MEDIUM_GRID, MEDIUM_RH_RANGE
from app.difficulty.quantize import quantize_part
from app.difficulty.range_shift import shift_into_range
from app.export import export_musicxml
from app.jobs import set_failed, set_result, set_status
from app.melody.extract import build_melody_part, extract_melody_notes
from app.notation.hand_split import SECONDS_PER_QUARTER, build_grand_staff_score
from app.separation.separator import separate_stems
from app.storage import evict_oldest_songs, write_metadata


def _rh_variants(melody_notes, seconds_per_quarter: float = SECONDS_PER_QUARTER):
    """Build the three difficulty tiers' RH Parts from one cleaned melody
    base — Easy/Medium reuse Spec 1's own quantize_part (thins note
    density to the grid) and shift_into_range (narrows register) so the
    right hand actually gets harder as the tier increases; Hard keeps the
    full-detail base unchanged, same "no further simplification"
    philosophy as Spec 1's Hard tier."""
    base = build_melody_part(melody_notes, seconds_per_quarter)
    return {
        "easy": shift_into_range(quantize_part(base, EASY_GRID), *EASY_RH_RANGE),
        "medium": shift_into_range(quantize_part(base, MEDIUM_GRID), *MEDIUM_RH_RANGE),
        "hard": base,
    }


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
        chords, seconds_per_quarter = detect_chords(str(harmony_path))
        if not chords:
            raise ValueError("No chords detected")

        set_status(job_id, "arranging")
        variants = generate_lh_variants(chords, seconds_per_quarter)
        rh_variants = _rh_variants(melody_notes, seconds_per_quarter)

        difficulties = {}
        for tier, lh_part in (("easy", variants.easy), ("medium", variants.medium), ("hard", variants.hard)):
            score = build_grand_staff_score(rh_variants[tier], lh_part, title=title)
            export_musicxml(score, dest_dir / f"{tier}.musicxml")
            difficulties[tier] = {"musicxml_url": f"/storage/{song_id}/{tier}.musicxml"}

        write_metadata(song_id, title=title, source_type=source_type, source_url=source_url, pipeline="arrange")
        evict_oldest_songs()

        set_result(job_id, {"song_id": song_id, "title": title, "difficulties": difficulties})
    except Exception as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        set_failed(job_id, str(exc))
