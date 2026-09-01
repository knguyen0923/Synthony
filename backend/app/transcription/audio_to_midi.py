from basic_pitch import ICASSP_2022_MODEL_PATH
from basic_pitch.inference import predict

from app.notation.types import NoteEvent


def transcribe_audio_to_notes(audio_path: str) -> list[NoteEvent]:
    _, _, note_events = predict(audio_path, ICASSP_2022_MODEL_PATH)
    return [
        NoteEvent(
            start=start,
            end=end,
            pitch=pitch,
            velocity=min(max(amplitude, 0.0), 1.0),
        )
        for start, end, pitch, amplitude, _pitch_bend in note_events
    ]
