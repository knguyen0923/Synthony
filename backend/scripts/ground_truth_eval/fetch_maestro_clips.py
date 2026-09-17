#!/usr/bin/env python3
"""One-time setup script: downloads the 5 (audio, MIDI) pairs named in
clips.CLIPS from MAESTRO v3.0.0's official public hosting into assets/.

Uses remotezip to fetch only the needed members from Google's public
GCS-hosted zips (~108GB audio zip, ~58MB MIDI-only zip) via HTTP range
requests -- never downloads either zip in full. Safe to re-run: skips any
clip file that already exists in assets/.

USAGE
  cd backend/scripts/ground_truth_eval
  ../../.venv/bin/python fetch_maestro_clips.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from remotezip import RemoteZip

sys.path.insert(0, str(Path(__file__).parent))
from clips import CLIPS  # noqa: E402

ASSETS_DIR = Path(__file__).parent / "assets"

_AUDIO_ZIP_URL = "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0.zip"
_MIDI_ZIP_URL = "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/maestro-v3.0.0-midi.zip"
_ZIP_ROOT = "maestro-v3.0.0/"


def _fetch_one(zip_url: str, member_path: str, dest: Path) -> None:
    if dest.exists():
        print(f"  already have {dest.name}, skipping")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with RemoteZip(zip_url) as zf, zf.open(_ZIP_ROOT + member_path) as src:
        dest.write_bytes(src.read())
    print(f"  fetched {dest.name} ({dest.stat().st_size} bytes)")


def main() -> int:
    for clip in CLIPS:
        print(f"[{clip['name']}]")
        _fetch_one(_AUDIO_ZIP_URL, clip["audio_filename"], ASSETS_DIR / f"{clip['name']}.wav")
        _fetch_one(_MIDI_ZIP_URL, clip["midi_filename"], ASSETS_DIR / f"{clip['name']}.midi")
    print(f"\nDone. Clips in {ASSETS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
