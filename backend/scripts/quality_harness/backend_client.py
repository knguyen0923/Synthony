"""Minimal client for driving the real, unmodified Synthony FastAPI backend
over HTTP — no mocking. Starts a real `uvicorn` process against the
checked-out `backend/` app, submits real audio through `/transcribe` or
`/arrange`, and polls jobs to completion exactly the way a real client
(or the project's established manual-verification workflow) would.

Kept deliberately dependency-light (stdlib + requests, both already
available in backend/.venv) so this harness has no extra install cost.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

# This file lives at backend/scripts/quality_harness/backend_client.py, so
# the repo's backend/ directory is three levels up. Resolved relative to
# this file (not hardcoded) so the harness works regardless of where the
# repo is checked out.
BACKEND_DIR = Path(__file__).resolve().parents[2]
PYTHON_BIN = BACKEND_DIR / ".venv" / "bin" / "python"


def find_free_port(start: int = 8931, end: int = 8999) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"No free port found in [{start}, {end})")


@dataclass
class BackendHandle:
    process: subprocess.Popen
    port: int

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def start_backend(port: Optional[int] = None, timeout_s: float = 60.0) -> BackendHandle:
    """Boot the real, unmodified app (app.main:app) with uvicorn against a
    free local port, using the project's own venv interpreter. This is the
    exact same command the project's documented verification workflow uses
    (`cd backend && ./.venv/bin/python -m uvicorn app.main:app --port <port>`),
    just launched from a script instead of by hand."""
    if port is None:
        port = find_free_port()

    proc = subprocess.Popen(
        [str(PYTHON_BIN), "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    handle = BackendHandle(process=proc, port=port)

    deadline = time.time() + timeout_s
    last_err = None
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(f"backend process exited early (code {proc.returncode}):\n{out}")
        try:
            r = requests.get(f"{handle.base_url}/health", timeout=1.0)
            if r.status_code == 200:
                return handle
        except requests.exceptions.RequestException as exc:
            last_err = exc
        time.sleep(0.5)

    handle.stop()
    raise RuntimeError(f"backend did not become healthy within {timeout_s}s (last error: {last_err})")


def submit_transcribe(
    base_url: str,
    *,
    audio_path: Optional[Path] = None,
    youtube_url: Optional[str] = None,
    timeout_s: float = 600.0,
) -> dict:
    """POST /transcribe (synchronous) and return the parsed JSON body."""
    files = None
    data = None
    try:
        if audio_path is not None:
            f = open(audio_path, "rb")
            files = {"audio_file": (audio_path.name, f, "application/octet-stream")}
            resp = requests.post(f"{base_url}/transcribe", files=files, timeout=timeout_s)
        elif youtube_url is not None:
            data = {"youtube_url": youtube_url}
            resp = requests.post(f"{base_url}/transcribe", data=data, timeout=timeout_s)
        else:
            raise ValueError("must supply audio_path or youtube_url")
    finally:
        if files is not None:
            files["audio_file"][1].close()

    if resp.status_code != 200:
        raise RuntimeError(f"/transcribe failed: {resp.status_code} {resp.text}")
    return resp.json()


def submit_arrange_and_wait(
    base_url: str,
    *,
    audio_path: Optional[Path] = None,
    youtube_url: Optional[str] = None,
    poll_interval_s: float = 2.0,
    timeout_s: float = 900.0,
) -> dict:
    """POST /arrange (async job), then poll /arrange/{job_id} until it
    reaches a terminal state. Returns the terminal payload (either the
    transcribe-shaped success body, or {"status": "failed", "detail": ...})."""
    files = None
    try:
        if audio_path is not None:
            f = open(audio_path, "rb")
            files = {"audio_file": (audio_path.name, f, "application/octet-stream")}
            resp = requests.post(f"{base_url}/arrange", files=files, timeout=60.0)
        elif youtube_url is not None:
            resp = requests.post(f"{base_url}/arrange", data={"youtube_url": youtube_url}, timeout=60.0)
        else:
            raise ValueError("must supply audio_path or youtube_url")
    finally:
        if files is not None:
            files["audio_file"][1].close()

    if resp.status_code != 202:
        raise RuntimeError(f"/arrange submit failed: {resp.status_code} {resp.text}")
    job_id = resp.json()["job_id"]

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        payload = requests.get(f"{base_url}/arrange/{job_id}", timeout=30.0).json()
        if "song_id" in payload or payload.get("status") == "failed":
            return payload
        time.sleep(poll_interval_s)

    raise RuntimeError(f"/arrange job {job_id} did not complete within {timeout_s}s")


def fetch_musicxml(base_url: str, song_id: str, tier: str, dest_path: Path) -> Path:
    resp = requests.get(f"{base_url}/storage/{song_id}/{tier}.musicxml", timeout=30.0)
    resp.raise_for_status()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(resp.content)
    return dest_path
