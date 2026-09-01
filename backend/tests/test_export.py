from music21 import stream, note

from app.export import export_musicxml


def test_export_writes_a_musicxml_file(tmp_path):
    score = stream.Score()
    part = stream.Part(id="RH")
    part.insert(0.0, note.Note("C4"))
    score.insert(0, part)

    output_path = tmp_path / "nested" / "easy.musicxml"
    result = export_musicxml(score, output_path)

    assert result == output_path
    assert output_path.exists()
    assert "<score-partwise" in output_path.read_text()
