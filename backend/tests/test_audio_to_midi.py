from app.notation.types import PedalEvent
from app.transcription.audio_to_midi import transcribe_audio_to_notes, transcribe_piano_audio_to_notes


def test_transcribe_detects_note_near_a4(synthetic_piano_wav):
    notes = transcribe_audio_to_notes(str(synthetic_piano_wav))

    assert len(notes) >= 1
    pitches = [n.pitch for n in notes]
    assert any(abs(p - 69) <= 2 for p in pitches)  # A4 = MIDI 69, +/-2 semitone tolerance


def test_transcribe_omitting_minimum_note_length_calls_predict_exactly_as_before(monkeypatch):
    """Regression guard for RH: transcribe_audio_to_notes's default
    behavior (no minimum_note_length argument) must call Basic Pitch's
    predict() with no minimum_note_length kwarg at all, not merely with
    its default value — so RH's call site (app/melody/extract.py, which
    never passes this new param) is byte-for-byte unchanged."""
    import app.transcription.audio_to_midi as audio_to_midi_module

    calls = []

    def fake_predict(audio_path, model_or_model_path, **kwargs):
        calls.append((audio_path, model_or_model_path, kwargs))
        return ({}, None, [])

    monkeypatch.setattr(audio_to_midi_module, "predict", fake_predict)

    transcribe_audio_to_notes("fake/path.wav")

    assert len(calls) == 1
    audio_path, model_or_model_path, kwargs = calls[0]
    assert audio_path == "fake/path.wav"
    assert model_or_model_path is audio_to_midi_module.ICASSP_2022_MODEL_PATH
    assert kwargs == {}


def test_transcribe_with_minimum_note_length_passes_it_through_to_predict(monkeypatch):
    import app.transcription.audio_to_midi as audio_to_midi_module

    calls = []

    def fake_predict(audio_path, model_or_model_path, **kwargs):
        calls.append((audio_path, model_or_model_path, kwargs))
        return ({}, None, [])

    monkeypatch.setattr(audio_to_midi_module, "predict", fake_predict)

    transcribe_audio_to_notes("fake/path.wav", minimum_note_length=180)

    assert len(calls) == 1
    _, _, kwargs = calls[0]
    assert kwargs == {"minimum_note_length": 180}


def test_transcribe_piano_detects_note_near_a4(synthetic_piano_note_wav):
    result = transcribe_piano_audio_to_notes(str(synthetic_piano_note_wav))

    assert len(result.notes) >= 1
    pitches = [n.pitch for n in result.notes]
    assert any(abs(p - 69) <= 2 for p in pitches)  # A4 = MIDI 69, +/-2 semitone tolerance


def test_transcribe_piano_converts_est_pedal_events_to_pedal_events(monkeypatch):
    """The piano model's transcribe() call returns est_pedal_events (a list
    of {onset_time, offset_time} dicts, seconds) from its dedicated pedal-
    detection head, alongside est_note_events. This must be captured and
    converted to PedalEvent, not silently discarded as before."""
    import pretty_midi

    import app.transcription.audio_to_midi as audio_to_midi_module

    class FakeTranscriptor:
        def transcribe(self, audio, midi_path):
            midi = pretty_midi.PrettyMIDI()
            instrument = pretty_midi.Instrument(program=0)
            instrument.notes.append(pretty_midi.Note(velocity=100, pitch=69, start=0.1, end=0.5))
            midi.instruments.append(instrument)
            midi.write(midi_path)
            return {
                "output_dict": {},
                "est_note_events": [],
                "est_pedal_events": [
                    {"onset_time": 7.390, "offset_time": 7.962},
                    {"onset_time": 10.0, "offset_time": 10.5},
                ],
            }

    monkeypatch.setattr(audio_to_midi_module, "_get_piano_transcriptor", lambda: FakeTranscriptor())
    monkeypatch.setattr(
        audio_to_midi_module.librosa, "load", lambda path, sr, mono: ([0.0] * 100, sr)
    )

    result = audio_to_midi_module.transcribe_piano_audio_to_notes("fake/path.wav")

    assert len(result.notes) == 1
    assert result.notes[0].pitch == 69
    assert result.pedal_events == [
        PedalEvent(start=7.390, end=7.962),
        PedalEvent(start=10.0, end=10.5),
    ]


def test_transcribe_piano_handles_no_pedal_events(monkeypatch):
    """The post-processor can return est_pedal_events=None when no pedal
    activity is detected at all — must convert to an empty list, not crash."""
    import pretty_midi

    import app.transcription.audio_to_midi as audio_to_midi_module

    class FakeTranscriptor:
        def transcribe(self, audio, midi_path):
            midi = pretty_midi.PrettyMIDI()
            midi.write(midi_path)
            return {"output_dict": {}, "est_note_events": [], "est_pedal_events": None}

    monkeypatch.setattr(audio_to_midi_module, "_get_piano_transcriptor", lambda: FakeTranscriptor())
    monkeypatch.setattr(
        audio_to_midi_module.librosa, "load", lambda path, sr, mono: ([0.0] * 100, sr)
    )

    result = audio_to_midi_module.transcribe_piano_audio_to_notes("fake/path.wav")

    assert result.notes == []
    assert result.pedal_events == []


def test_piano_checkpoint_downloaded_true_when_file_exists_and_is_large_enough(tmp_path, monkeypatch):
    import app.transcription.audio_to_midi as audio_to_midi_module

    # Patch the size threshold down too -- writing a real
    # _MIN_CHECKPOINT_SIZE_BYTES-sized (160MB) file just to satisfy this
    # check would make the test slow and disk-heavy for no reason.
    fake_checkpoint = tmp_path / "checkpoint.pth"
    fake_checkpoint.write_bytes(b"x" * 100)
    monkeypatch.setattr(audio_to_midi_module, "_PIANO_CHECKPOINT_PATH", fake_checkpoint)
    monkeypatch.setattr(audio_to_midi_module, "_MIN_CHECKPOINT_SIZE_BYTES", 100)

    assert audio_to_midi_module.piano_checkpoint_downloaded() is True


def test_piano_checkpoint_downloaded_false_when_file_is_missing(tmp_path, monkeypatch):
    import app.transcription.audio_to_midi as audio_to_midi_module

    monkeypatch.setattr(audio_to_midi_module, "_PIANO_CHECKPOINT_PATH", tmp_path / "does-not-exist.pth")

    assert audio_to_midi_module.piano_checkpoint_downloaded() is False


def test_piano_checkpoint_downloaded_false_when_file_is_truncated(tmp_path, monkeypatch):
    import app.transcription.audio_to_midi as audio_to_midi_module

    truncated = tmp_path / "checkpoint.pth"
    truncated.write_bytes(b"x" * 10)  # far below the (patched) threshold
    monkeypatch.setattr(audio_to_midi_module, "_PIANO_CHECKPOINT_PATH", truncated)
    monkeypatch.setattr(audio_to_midi_module, "_MIN_CHECKPOINT_SIZE_BYTES", 100)

    assert audio_to_midi_module.piano_checkpoint_downloaded() is False
