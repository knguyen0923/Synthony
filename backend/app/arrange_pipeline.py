import logging
import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.io import wavfile

from app.chords.detect import detect_key_and_tempo
from app.concurrency import JOB_QUEUE_TIMEOUT_SECONDS, NoJobSlotAvailable, job_slot
from app.difficulty.easy import EASY_GRID, EASY_LH_RANGE, EASY_RH_RANGE
from app.difficulty.medium import MAX_VOICING_TONES, MEDIUM_GRID, MEDIUM_LH_RANGE, MEDIUM_RH_RANGE
from app.difficulty.quantize import quantize_part
from app.difficulty.range_shift import shift_into_range
from app.export import export_musicxml
from app.jobs import set_failed, set_result, set_status
from app.lh.extract import HARD_LH_RANGE, LH_MINIMUM_NOTE_LENGTH_MS, build_lh_part, extract_lh_notes
from app.melody.extract import build_melody_part, extract_melody_notes
from app.notation.hand_split import (
    MAX_SIMULTANEOUS_VOICES_PER_HAND,
    SECONDS_PER_QUARTER,
    build_grand_staff_score,
    key_signature_from_tonic,
    notes_to_part,
)
from app.notation.voice_cap import cap_simultaneous_notes
from app.separation.separator import separate_stems
from app.storage import evict_oldest_songs, write_metadata
from app.tempo.detect import BeatMap, detect_beat_map
from app.transcription.audio_to_midi import transcribe_audio_to_notes

logger = logging.getLogger(__name__)

# A real sung melody produces a much higher rate of detected notes per
# second than a near-silent/noise-only vocals stem (genuinely instrumental
# input) — this is a *density*, not a raw count, because a real vocal clip
# and a genuinely instrumental full-length song differ enormously in
# duration: a short real-vocal clip and a long instrumental track can have
# similar total note counts while differing ~5-8x in density. First-pass
# tuning constant, empirically set from real-audio verification (corpus
# A/B/C measured at 1.47-2.66 notes/s; one real instrumental track measured
# at 0.32 notes/s) — expect to adjust further as more real audio is tested.
MIN_MELODY_NOTE_DENSITY = 0.8  # notes per second

# Below this many notes there typically isn't a long enough span to compute
# a meaningful density (e.g. 0 or 1 notes give an undefined or degenerate
# span) — treat anything this thin as instrumental outright, matching the
# original predicate's behavior for the near-empty case.
MIN_MELODY_NOTES_FOR_DENSITY_CHECK = 2


def _melody_note_density(melody_notes: list) -> float:
    """Notes-per-second rate over the span from the first note's start to
    the last note's end. Returns 0.0 (unambiguously below any sane
    threshold) when there aren't enough notes, or the span is degenerate,
    to compute a meaningful rate."""
    if len(melody_notes) < MIN_MELODY_NOTES_FOR_DENSITY_CHECK:
        return 0.0
    span = melody_notes[-1].end - melody_notes[0].start
    if span <= 0:
        return 0.0
    return len(melody_notes) / span


def _is_instrumental(melody_notes: list) -> bool:
    """True when extract_melody_notes's output has an implausibly low note
    rate for a real sung melody — treated as "no real vocal content,"
    routing run_arrange_pipeline to the instrumental path instead of
    building RH from near-empty or noise-artifact notes. Uses note density
    (see _melody_note_density) rather than a raw count, because real-audio
    verification found raw count is confounded with clip duration."""
    return _melody_note_density(melody_notes) < MIN_MELODY_NOTE_DENSITY


def _rh_variants(melody_notes, seconds_per_quarter: float = SECONDS_PER_QUARTER, beat_map: Optional[BeatMap] = None):
    """Build the three difficulty tiers' RH Parts from one cleaned melody
    base — Easy/Medium reuse Spec 1's own quantize_part (thins note
    density to the grid) and shift_into_range (narrows register) so the
    right hand actually gets harder as the tier increases; Hard keeps the
    full-detail base unchanged, same "no further simplification"
    philosophy as Spec 1's Hard tier."""
    base = build_melody_part(melody_notes, seconds_per_quarter, beat_map)
    return {
        "easy": shift_into_range(quantize_part(base, EASY_GRID), *EASY_RH_RANGE),
        "medium": shift_into_range(quantize_part(base, MEDIUM_GRID), *MEDIUM_RH_RANGE),
        "hard": base,
    }


def _lh_variants(harmony_path: str, seconds_per_quarter: float = SECONDS_PER_QUARTER, beat_map: Optional[BeatMap] = None):
    """Build the three difficulty tiers' LH Parts from one real
    transcription of the harmony audio — same shape as _rh_variants:
    Easy/Medium derive from the Hard base via quantize_part(max_voices)
    (thinning both note density and simultaneous-voice count) and
    shift_into_range; Hard is the transcription itself, unmodified."""
    notes = extract_lh_notes(harmony_path)
    if not notes:
        raise ValueError("No harmonic content detected")
    base = build_lh_part(notes, seconds_per_quarter, beat_map)
    return {
        "easy": shift_into_range(quantize_part(base, EASY_GRID, max_voices=1), *EASY_LH_RANGE),
        "medium": shift_into_range(quantize_part(base, MEDIUM_GRID, max_voices=MAX_VOICING_TONES), *MEDIUM_LH_RANGE),
        "hard": base,
    }


def _instrumental_variants(
    bass_path: str, other_path: str, seconds_per_quarter: float = SECONDS_PER_QUARTER, beat_map: Optional[BeatMap] = None
):
    """RH/LH variants for a song with no real vocal melody (see
    _is_instrumental): transcribes the bass and "other" Demucs stems
    SEPARATELY -- bass -> LH, "other" -> RH -- instead of mixing them into
    one harmony signal and re-splitting by pitch continuity (assign_hands).
    Real-audio verification found the mixed+DP-split approach produces a
    reasonable RH/LH note-count balance but excessive hand-flicker (~44%
    of adjacent notes swapping hands) on real multi-instrument input,
    since continuity-based splitting assumes one performer's two hands,
    not two different instruments interleaved in time. Each hand's part is
    therefore one continuously-transcribed real source, avoiding flicker
    structurally rather than by tuning. See the design spec's
    "Post-implementation update" section for the real-audio evidence."""
    rh_notes = transcribe_audio_to_notes(other_path, minimum_note_length=LH_MINIMUM_NOTE_LENGTH_MS)
    lh_notes = transcribe_audio_to_notes(bass_path, minimum_note_length=LH_MINIMUM_NOTE_LENGTH_MS)
    if not rh_notes and not lh_notes:
        raise ValueError("No harmonic content detected")
    rh_notes = cap_simultaneous_notes(rh_notes, MAX_SIMULTANEOUS_VOICES_PER_HAND)
    lh_notes = cap_simultaneous_notes(lh_notes, MAX_SIMULTANEOUS_VOICES_PER_HAND)

    rh_base = notes_to_part(rh_notes, part_id="RH", seconds_per_quarter=seconds_per_quarter, beat_map=beat_map)
    lh_base = shift_into_range(
        notes_to_part(lh_notes, part_id="LH", seconds_per_quarter=seconds_per_quarter, beat_map=beat_map),
        *HARD_LH_RANGE,
    )

    rh_variants = {
        "easy": shift_into_range(quantize_part(rh_base, EASY_GRID, max_voices=1), *EASY_RH_RANGE),
        "medium": shift_into_range(quantize_part(rh_base, MEDIUM_GRID, max_voices=MAX_VOICING_TONES), *MEDIUM_RH_RANGE),
        "hard": rh_base,
    }
    lh_variants = {
        "easy": shift_into_range(quantize_part(lh_base, EASY_GRID, max_voices=1), *EASY_LH_RANGE),
        "medium": shift_into_range(quantize_part(lh_base, MEDIUM_GRID, max_voices=MAX_VOICING_TONES), *MEDIUM_LH_RANGE),
        "hard": lh_base,
    }
    return rh_variants, lh_variants


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
        logger.info("job %s: acquiring a job slot", job_id)
        with job_slot(blocking=True, timeout=JOB_QUEUE_TIMEOUT_SECONDS):
            set_status(job_id, "separating")
            stems = separate_stems(audio_path, dest_dir / "stems")

            set_status(job_id, "extracting_melody")
            melody_notes = extract_melody_notes(str(stems.vocals))

            set_status(job_id, "detecting_key")
            harmony_path = mix_wav_files(stems.bass, stems.other, dest_dir / "stems" / "harmony.wav")
            detected_key, seconds_per_quarter = detect_key_and_tempo(str(harmony_path))
            beat_map = detect_beat_map(str(harmony_path))

            set_status(job_id, "arranging")
            if _is_instrumental(melody_notes):
                logger.info(
                    "job %s: no real vocal melody detected (%d notes, %.2f notes/s), using DP hand-split",
                    job_id, len(melody_notes), _melody_note_density(melody_notes),
                )
                rh_variants, lh_variants = _instrumental_variants(str(stems.bass), str(stems.other), seconds_per_quarter, beat_map)
            else:
                lh_variants = _lh_variants(str(harmony_path), seconds_per_quarter, beat_map)
                rh_variants = _rh_variants(melody_notes, seconds_per_quarter, beat_map)

            difficulties = {}
            key_signature = key_signature_from_tonic(*detected_key)
            for tier in ("easy", "medium", "hard"):
                score = build_grand_staff_score(rh_variants[tier], lh_variants[tier], title=title, key_signature=key_signature)
                export_musicxml(score, dest_dir / f"{tier}.musicxml")
                difficulties[tier] = {"musicxml_url": f"/storage/{song_id}/{tier}.musicxml"}

            write_metadata(song_id, title=title, source_type=source_type, source_url=source_url, pipeline="arrange")
            evict_oldest_songs()

        set_result(job_id, {"song_id": song_id, "title": title, "difficulties": difficulties})
    except NoJobSlotAvailable as exc:
        logger.warning("arrange job %s rejected: %s", job_id, exc)
        shutil.rmtree(dest_dir, ignore_errors=True)
        set_failed(job_id, str(exc))
    except Exception as exc:
        logger.exception("arrange pipeline failed for job_id=%s song_id=%s", job_id, song_id)
        shutil.rmtree(dest_dir, ignore_errors=True)
        set_failed(job_id, str(exc))
