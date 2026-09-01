from app.transcription.audio_to_midi import transcribe_audio_to_notes


def test_transcribe_detects_note_near_a4(synthetic_piano_wav):
    notes = transcribe_audio_to_notes(str(synthetic_piano_wav))

    assert len(notes) >= 1
    pitches = [n.pitch for n in notes]
    assert any(abs(p - 69) <= 2 for p in pitches)  # A4 = MIDI 69, +/-2 semitone tolerance
