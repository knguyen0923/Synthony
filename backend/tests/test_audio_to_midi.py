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
    notes = transcribe_piano_audio_to_notes(str(synthetic_piano_note_wav))

    assert len(notes) >= 1
    pitches = [n.pitch for n in notes]
    assert any(abs(p - 69) <= 2 for p in pitches)  # A4 = MIDI 69, +/-2 semitone tolerance
