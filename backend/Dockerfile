FROM python:3.11-slim

# ffmpeg: yt-dlp needs it to extract audio from YouTube-link input.
# fluidsynth: only needed by the test suite's synthetic_piano_note_wav
# fixture; harmless to include so `pytest` is runnable inside the image.
# build-essential + git: madmom's sdist compiles Cython extensions and is
# installed straight from its GitHub main branch (see requirements.txt).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fluidsynth build-essential git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Same two-step install as README's "Backend" section: madmom's setup.py
# imports numpy/scipy/Cython/mido directly (not declared as PEP 517 build
# requirements), so they must already be present, and the install itself
# needs --no-build-isolation.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "numpy>=1.26.4,<2.0" scipy cython mido "setuptools<81" \
    && pip install --no-cache-dir --no-build-isolation -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
