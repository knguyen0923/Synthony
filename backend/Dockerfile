FROM python:3.11-slim

# ffmpeg: yt-dlp needs it to extract audio from YouTube-link input.
# fluidsynth: only needed by the test suite's synthetic_piano_note_wav
# fixture; harmless to include even though tests aren't copied/run in
# this image (only `app` is — see the COPY below).
# build-essential + git: madmom's sdist compiles Cython extensions and is
# installed straight from its GitHub main branch (see requirements.txt).
# curl + cmake + libopus-dev: needed to build `sphn` (a transitive
# dependency pulled in via `demucs`) from source on linux/aarch64 — see
# the rustup/maturin note below. libopus-dev provides the system Opus
# library so sphn's transitive `audiopus_sys` crate links against it
# instead of vendor-building libopus from source.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fluidsynth build-essential git curl cmake libopus-dev \
    && rm -rf /var/lib/apt/lists/*

# `sphn` (a transitive dependency pulled in via `demucs`) publishes PyPI
# wheels only for linux/x86_64 (manylinux), macOS-arm64, and Windows —
# there is no linux/aarch64 wheel, so on a native arm64 build pip falls
# back to building it from source. That needs a Rust toolchain (sphn is
# a PyO3/maturin extension) plus cmake and libopus-dev (installed above).
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable

WORKDIR /app

COPY requirements.txt .
# Same two-step install as README's "Backend" section: madmom's setup.py
# imports numpy/scipy/Cython/mido directly (not declared as PEP 517 build
# requirements), so they must already be present, and the install itself
# needs --no-build-isolation.
#
# `maturin` is needed here so pip can build `sphn` from source on
# linux/aarch64 (see the apt-get/rustup layers above); on linux/amd64
# hosts sphn just installs from its prebuilt wheel and maturin sits
# unused. Confirmed to build natively on both linux/amd64 and
# linux/arm64 hosts.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "numpy>=1.26.4,<2.0" scipy cython mido "setuptools<81" maturin \
    && pip install --no-cache-dir --no-build-isolation -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
