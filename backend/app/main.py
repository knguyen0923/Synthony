import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import librosa
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.arrange_pipeline import run_arrange_pipeline
from app.jobs import create_job, get_job
from app.ingestion.normalize import ingest, IngestionError
from app.transcription.audio_to_midi import transcribe_audio_to_notes
from app.notation.hand_split import notes_to_grand_staff
from app.difficulty.engine import generate_variants
from app.export import export_musicxml
from app.storage import (
    new_song_id,
    song_dir,
    write_metadata,
    evict_oldest_songs,
    read_song,
    list_songs,
    delete_song,
    STORAGE_ROOT,
)

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


class SongSummary(BaseModel):
    song_id: str
    title: str
    source_type: str
    source_url: Optional[str]
    pipeline: str = "transcribe"
    created_at: str


class ArrangeSubmitResponse(BaseModel):
    job_id: str
    status: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/songs", response_model=list[SongSummary])
def songs() -> list[dict]:
    return list_songs()


@app.get("/songs/{song_id}", response_model=TranscribeResponse)
def song(song_id: str) -> TranscribeResponse:
    metadata = read_song(song_id)
    if metadata is None:
        raise HTTPException(status_code=404, detail="Song not found")
    return TranscribeResponse(
        song_id=song_id,
        title=metadata["title"],
        difficulties={
            tier: DifficultyLink(musicxml_url=f"/storage/{song_id}/{tier}.musicxml")
            for tier in ("easy", "medium", "hard")
        },
    )


@app.delete("/songs/{song_id}", status_code=204)
def remove_song(song_id: str) -> None:
    if read_song(song_id) is None:
        raise HTTPException(status_code=404, detail="Song not found")
    delete_song(song_id)


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio_file: Optional[UploadFile] = File(None),
    youtube_url: Optional[str] = Form(None),
    spotify_url: Optional[str] = Form(None),
) -> TranscribeResponse:
    song_id = new_song_id()
    dest_dir = song_dir(song_id)

    try:
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
                    max_duration_seconds=MAX_DURATION_SECONDS,
                )
            except IngestionError as exc:
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        duration = librosa.get_duration(path=str(ingested.path))
        if duration > MAX_DURATION_SECONDS:
            raise HTTPException(status_code=413, detail="Audio exceeds the 10-minute duration cap")

        notes = transcribe_audio_to_notes(str(ingested.path))
        if not notes:
            raise HTTPException(status_code=422, detail="No pitched content detected")

        title = ingested.title
        score = notes_to_grand_staff(notes, title=title)
        variants = generate_variants(score)

        for tier, variant_score in (
            ("easy", variants.easy),
            ("medium", variants.medium),
            ("hard", variants.hard),
        ):
            export_musicxml(variant_score, dest_dir / f"{tier}.musicxml")

        write_metadata(song_id, title=title, source_type=ingested.source_type, source_url=ingested.source_url)
        evict_oldest_songs()
    except Exception:
        # song_dir() already created dest_dir before any of the above ran;
        # any failure past that point (a rejected upload, a duration-cap
        # violation, no pitched content, a downloaded-but-unusable YouTube
        # file, ...) must not leave an orphan directory — or, for YouTube
        # input, an orphan downloaded audio file — behind under STORAGE_ROOT.
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise

    return TranscribeResponse(
        song_id=song_id,
        title=title,
        difficulties={
            tier: DifficultyLink(musicxml_url=f"/storage/{song_id}/{tier}.musicxml")
            for tier in ("easy", "medium", "hard")
        },
    )


@app.post("/arrange", response_model=ArrangeSubmitResponse, status_code=202)
async def arrange(
    background_tasks: BackgroundTasks,
    audio_file: Optional[UploadFile] = File(None),
    youtube_url: Optional[str] = Form(None),
    spotify_url: Optional[str] = Form(None),
) -> ArrangeSubmitResponse:
    song_id = new_song_id()
    dest_dir = song_dir(song_id)

    try:
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
                    max_duration_seconds=MAX_DURATION_SECONDS,
                )
            except IngestionError as exc:
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        duration = librosa.get_duration(path=str(ingested.path))
        if duration > MAX_DURATION_SECONDS:
            raise HTTPException(status_code=413, detail="Audio exceeds the 10-minute duration cap")
    except Exception:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise

    job_id = create_job()
    background_tasks.add_task(
        run_arrange_pipeline,
        job_id=job_id,
        audio_path=str(ingested.path),
        title=ingested.title,
        source_type=ingested.source_type,
        source_url=ingested.source_url,
        song_id=song_id,
        dest_dir=dest_dir,
    )
    return ArrangeSubmitResponse(job_id=job_id, status="processing")


@app.get("/arrange/{job_id}")
def arrange_status(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "done":
        return job.result
    if job.status == "failed":
        return {"status": "failed", "detail": job.detail}
    return {"status": job.status}
