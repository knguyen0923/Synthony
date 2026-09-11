import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import librosa
import pretty_midi
from basic_pitch import ICASSP_2022_MODEL_PATH
from basic_pitch.inference import predict
from piano_transcription_inference import PianoTranscription, sample_rate as PIANO_MODEL_SAMPLE_RATE

from app.notation.types import NoteEvent, PedalEvent

# The library's own checkpoint fetch shells out to `wget`, which isn't
# guaranteed to be on PATH (it wasn't on the dev machine this was built on).
# We fetch it ourselves with urllib and hand the library an explicit path so
# its wget-based fallback never runs.
_PIANO_CHECKPOINT_PATH = Path.home() / "piano_transcription_inference_data" / "note_F1=0.9677_pedal_F1=0.9186.pth"
_PIANO_CHECKPOINT_URL = "https://zenodo.org/record/4034264/files/CRNN_note_F1%3D0.9677_pedal_F1%3D0.9186.pth?download=1"
_MIN_CHECKPOINT_SIZE_BYTES = 1.6e8  # matches the library's own corrupt-download check

_piano_transcriptor = None


def transcribe_audio_to_notes(audio_path: str, minimum_note_length: Optional[float] = None) -> list[NoteEvent]:
    """Run Basic Pitch on `audio_path`.

    minimum_note_length, when given, is passed through to Basic Pitch's
    predict() as-is (its units are milliseconds; Basic Pitch's own default
    is 127.7). Left as None (the default), predict() is called exactly as
    before — no keyword is added to the call — so this stays a strict
    no-op for existing callers (currently RH's melody extraction)."""
    predict_kwargs = {} if minimum_note_length is None else {"minimum_note_length": minimum_note_length}
    _, _, note_events = predict(audio_path, ICASSP_2022_MODEL_PATH, **predict_kwargs)
    return [
        NoteEvent(
            start=start,
            end=end,
            pitch=pitch,
            velocity=min(max(amplitude, 0.0), 1.0),
        )
        for start, end, pitch, amplitude, _pitch_bend in note_events
    ]


def _ensure_piano_checkpoint() -> Path:
    if not _PIANO_CHECKPOINT_PATH.exists() or _PIANO_CHECKPOINT_PATH.stat().st_size < _MIN_CHECKPOINT_SIZE_BYTES:
        _PIANO_CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(_PIANO_CHECKPOINT_URL, _PIANO_CHECKPOINT_PATH)
    return _PIANO_CHECKPOINT_PATH


def _get_piano_transcriptor() -> PianoTranscription:
    global _piano_transcriptor
    if _piano_transcriptor is None:
        _piano_transcriptor = PianoTranscription(device="cpu", checkpoint_path=str(_ensure_piano_checkpoint()))
    return _piano_transcriptor


@dataclass(frozen=True)
class PianoTranscriptionResult:
    """transcribe_piano_audio_to_notes's return shape: the transcribed notes
    plus the sustain-pedal events the model's dedicated pedal-detection head
    also produces (previously discarded) — used to notate pedal marks
    rather than leaving pedal-inflated note offsets unexplained."""
    notes: list[NoteEvent]
    pedal_events: list[PedalEvent]


def transcribe_piano_audio_to_notes(audio_path: str) -> PianoTranscriptionResult:
    """Piano-specialized transcription (ByteDance's high-resolution piano
    transcription model, MAESTRO-trained) for audio already known to be a
    solo piano performance — Spec 1's use case. Not suitable for Spec 2's
    vocal or mixed-accompaniment stems, which stay on transcribe_audio_to_notes."""
    transcriptor = _get_piano_transcriptor()
    # Bypass the library's own load_audio(): it calls a librosa API removed
    # in librosa>=0.10, which is what's pinned in this project.
    audio, _ = librosa.load(audio_path, sr=PIANO_MODEL_SAMPLE_RATE, mono=True)

    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        transcribed = transcriptor.transcribe(audio, tmp_path)
        midi = pretty_midi.PrettyMIDI(tmp_path)
    finally:
        os.unlink(tmp_path)

    notes = [
        NoteEvent(
            start=note.start,
            end=note.end,
            pitch=note.pitch,
            velocity=min(max(note.velocity / 127.0, 0.0), 1.0),
        )
        for instrument in midi.instruments
        for note in instrument.notes
    ]
    pedal_events = [
        PedalEvent(start=event["onset_time"], end=event["offset_time"])
        for event in (transcribed.get("est_pedal_events") or [])
    ]
    return PianoTranscriptionResult(notes=notes, pedal_events=pedal_events)
