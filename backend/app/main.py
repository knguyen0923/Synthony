import os
import tempfile
from pathlib import Path
from typing import Optional

import librosa
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.ingestion.normalize import ingest, IngestionError
from app.transcription.audio_to_midi import transcribe_audio_to_notes
from app.notation.hand_split import notes_to_grand_staff
from app.difficulty.engine import generate_variants
from app.export import export_musicxml
from app.storage import new_song_id, song_dir, write_metadata, STORAGE_ROOT

MAX_DURATION_SECONDS = 600  # 10 minutes

# Required only for Spotify-link input (resolved via Spotify's Web API,
# then matched and downloaded through YouTube — see ingestion/spotify.py).
# Create an app at https://developer.spotify.com/dashboard to obtain these.
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")

STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/storage", StaticFiles(directory=str(STORAGE_ROOT)), name="storage")


class DifficultyLink(BaseModel):
    musicxml_url: str


class TranscribeResponse(BaseModel):
    song_id: str
    title: str
    difficulties: dict[str, DifficultyLink]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio_file: Optional[UploadFile] = File(None),
    youtube_url: Optional[str] = Form(None),
    spotify_url: Optional[str] = Form(None),
) -> TranscribeResponse:
    song_id = new_song_id()
    dest_dir = song_dir(song_id)

    with tempfile.TemporaryDirectory() as tmp:
        upload_tmp_path = None
        upload_filename = None
        if audio_file is not None:
            upload_tmp_path = Path(tmp) / Path(audio_file.filename or "upload").name
            upload_tmp_path.write_bytes(await audio_file.read())
            upload_filename = audio_file.filename

        try:
            ingested = ingest(
                dest_dir,
                uploaded_file_path=upload_tmp_path,
                uploaded_filename=upload_filename,
                youtube_url=youtube_url,
                spotify_url=spotify_url,
                spotify_client_id=SPOTIFY_CLIENT_ID,
                spotify_client_secret=SPOTIFY_CLIENT_SECRET,
            )
        except IngestionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    duration = librosa.get_duration(path=str(ingested.path))
    if duration > MAX_DURATION_SECONDS:
        raise HTTPException(status_code=413, detail="Audio exceeds the 10-minute duration cap")

    notes = transcribe_audio_to_notes(str(ingested.path))
    if not notes:
        raise HTTPException(status_code=422, detail="No pitched content detected")

    score = notes_to_grand_staff(notes)
    variants = generate_variants(score)

    for tier, variant_score in (
        ("easy", variants.easy),
        ("medium", variants.medium),
        ("hard", variants.hard),
    ):
        export_musicxml(variant_score, dest_dir / f"{tier}.musicxml")

    title = ingested.title
    write_metadata(song_id, title=title, source_type=ingested.source_type, source_url=ingested.source_url)

    return TranscribeResponse(
        song_id=song_id,
        title=title,
        difficulties={
            tier: DifficultyLink(musicxml_url=f"/storage/{song_id}/{tier}.musicxml")
            for tier in ("easy", "medium", "hard")
        },
    )
