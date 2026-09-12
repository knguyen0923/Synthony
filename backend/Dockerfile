FROM python:3.11-slim

# ffmpeg: yt-dlp needs it to extract audio from YouTube-link input.
# fluidsynth: only needed by the test suite's synthetic_piano_note_wav
# fixture; harmless to include even though tests aren't copied/run in
# this image (only `app` is — see the COPY below).
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
#
# Known limitation on Apple Silicon / arm64 Docker hosts: `sphn` (a
# transitive dependency pulled in via `demucs`) publishes PyPI wheels only
# for linux/x86_64 (manylinux), macOS-arm64, and Windows — there is no
# linux/aarch64 wheel. On a native arm64 build, pip falls back to building
# sphn from source, which needs the `maturin` Rust build backend (not
# installed here) and fails with "Cannot import 'maturin'". This image
# builds fine on linux/amd64 hosts (confirmed). On an arm64 host, build
# under emulation instead: `docker compose build --platform linux/amd64
# backend` (slow under QEMU, and the resulting image also runs emulated).
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "numpy>=1.26.4,<2.0" scipy cython mido "setuptools<81" \
    && pip install --no-cache-dir --no-build-isolation -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
