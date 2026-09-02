from scipy.io import wavfile

from app.separation.separator import separate_stems


def test_separate_stems_produces_all_four_stems_matching_input_duration(synthetic_piano_wav, tmp_path):
    input_rate, input_audio = wavfile.read(str(synthetic_piano_wav))
    input_duration = len(input_audio) / input_rate

    stems = separate_stems(str(synthetic_piano_wav), tmp_path / "separated")

    for stem_path in (stems.vocals, stems.drums, stems.bass, stems.other):
        assert stem_path.exists()
        rate, audio = wavfile.read(str(stem_path))
        duration = len(audio) / rate
        assert abs(duration - input_duration) < 0.5  # Demucs may pad slightly
