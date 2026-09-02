import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.io import wavfile

from app.chords.detect import detect_key_and_tempo
from app.difficulty.easy import EASY_GRID, EASY_LH_RANGE, EASY_RH_RANGE
from app.difficulty.medium import MEDIUM_GRID, MEDIUM_LH_RANGE, MEDIUM_RH_RANGE
from app.difficulty.quantize import quantize_part
from app.difficulty.range_shift import shift_into_range
from app.export import export_musicxml
from app.jobs import set_failed, set_result, set_status
from app.lh.extract import build_lh_part, extract_lh_notes
from app.melody.extract import build_melody_part, extract_melody_notes
from app.notation.hand_split import SECONDS_PER_QUARTER, build_grand_staff_score, key_signature_from_tonic
from app.separation.separator import separate_stems
from app.storage import evict_oldest_songs, write_metadata

MEDIUM_LH_MAX_VOICES = 3  # matches the previous arrangement/medium.py's MAX_BLOCK_TONES


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


def _lh_variants(harmony_path: str, seconds_per_quarter: float = SECONDS_PER_QUARTER):
    """Build the three difficulty tiers' LH Parts from one real
    transcription of the harmony audio — same shape as _rh_variants:
    Easy/Medium derive from the Hard base via quantize_part(max_voices)
    (thinning both note density and simultaneous-voice count) and
    shift_into_range; Hard is the transcription itself, unmodified."""
    notes = extract_lh_notes(harmony_path)
    if not notes:
        raise ValueError("No harmonic content detected")
    base = build_lh_part(notes, seconds_per_quarter)
    return {
        "easy": shift_into_range(quantize_part(base, EASY_GRID, max_voices=1), *EASY_LH_RANGE),
        "medium": shift_into_range(quantize_part(base, MEDIUM_GRID, max_voices=MEDIUM_LH_MAX_VOICES), *MEDIUM_LH_RANGE),
        "hard": base,
    }


def mix_wav_files(path_a: Path, path_b: Path, dest: Path) -> Path:
    """Sum two WAV files sample-for-sample into dest, normalizing to avoid
    clipping. Used to combine the bass+other stems into a single harmony
    signal for LH transcription and key/tempo detection."""
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

        set_status(job_id, "detecting_key")
        harmony_path = mix_wav_files(stems.bass, stems.other, dest_dir / "stems" / "harmony.wav")
        detected_key, seconds_per_quarter = detect_key_and_tempo(str(harmony_path))

        set_status(job_id, "arranging")
        lh_variants = _lh_variants(str(harmony_path), seconds_per_quarter)
        rh_variants = _rh_variants(melody_notes, seconds_per_quarter)

        difficulties = {}
        key_signature = key_signature_from_tonic(*detected_key)
        for tier in ("easy", "medium", "hard"):
            score = build_grand_staff_score(rh_variants[tier], lh_variants[tier], title=title, key_signature=key_signature)
            export_musicxml(score, dest_dir / f"{tier}.musicxml")
            difficulties[tier] = {"musicxml_url": f"/storage/{song_id}/{tier}.musicxml"}

        write_metadata(song_id, title=title, source_type=source_type, source_url=source_url, pipeline="arrange")
        evict_oldest_songs()

        set_result(job_id, {"song_id": song_id, "title": title, "difficulties": difficulties})
    except Exception as exc:
        shutil.rmtree(dest_dir, ignore_errors=True)
        set_failed(job_id, str(exc))
