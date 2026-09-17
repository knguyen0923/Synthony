#!/usr/bin/env python3
"""Reusable quality-evidence harness for the Synthony transcription/
arrangement pipelines.

Runs the REAL, unmodified backend (via a real subprocess + real HTTP
calls to /transcribe and /arrange — no mocking) against a fixed real-audio
test corpus, then:
  1. extracts objective, comparable metrics from the resulting MusicXML
     via music21 (note counts, pitch range, duration histogram,
     simultaneous-voice-count-over-time) for every difficulty tier,
  2. exports a MIDI file per tier for a human listening pass,
  3. copies the MIDI files into ~/Downloads/synthony-arrangements/ with a
     clearly labeled suffix,
  4. writes one combined metrics.json under output/<label>/ for
     programmatic before/after diffing.

USAGE
  cd /Users/knguyen/VSC/Synthony/backend/scripts/quality_harness
  /Users/knguyen/VSC/Synthony/backend/.venv/bin/python run_baseline.py --label baseline
  # ... later, after a sibling agent's change lands (merged/checked out) ...
  /Users/knguyen/VSC/Synthony/backend/.venv/bin/python run_baseline.py --label after-tempo-fix
  # then diff the two output/<label>/metrics.json files (see diff_metrics.py)

The audio corpus is fixed in SOURCES below so re-runs are apples-to-apples.

ASSET CORPUS NOTE (relocation, 2026-09-11)
  This harness originally lived outside the repo, under a Claude Code job's
  tmp directory, where it was at risk of being deleted by tmp cleanup. The
  Python scripts were moved into the repo at
  backend/scripts/quality_harness/ so they survive.

  The real-audio test corpus (assets/*.wav, assets/*.mp3 — ~25MB) was
  copied alongside the scripts to backend/scripts/quality_harness/assets/
  for local reuse, but it is intentionally listed in .gitignore and is
  NOT committed to git: binary audio/MIDI fixtures would permanently bloat
  the repo's history. If assets/ is ever missing (e.g. fresh checkout,
  or after local cleanup), it needs to be re-supplied out-of-band (see the
  SOURCES provenance notes below for what each file is) — it will not come
  back via `git pull`.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from backend_client import (  # noqa: E402
    start_backend,
    submit_transcribe,
    submit_arrange_and_wait,
    fetch_musicxml,
)
from metrics import analyze_musicxml, export_midi, save_json  # noqa: E402

HARNESS_DIR = Path(__file__).parent
ASSETS_DIR = HARNESS_DIR / "assets"
OUTPUT_DIR = HARNESS_DIR / "output"
DOWNLOADS_DIR = Path.home() / "Downloads" / "synthony-arrangements"

# Real MAESTRO clips fetched by the ground-truth eval (backlog item 2a) --
# reused here (not duplicated) for the difficulty-tier human-judgment
# validation (backlog item 2b), since both need the same real solo-piano
# recordings. See backend/scripts/ground_truth_eval/fetch_maestro_clips.py.
MAESTRO_ASSETS_DIR = HARNESS_DIR.parent / "ground_truth_eval" / "assets"

TIERS = ("easy", "medium", "hard")


@dataclass
class Source:
    name: str  # stable id used in filenames; keep constant across runs
    pipeline: str  # "transcribe" or "arrange"
    audio_path: Optional[Path] = None
    youtube_url: Optional[str] = None
    note: str = ""  # free-text provenance note, carried into metrics.json


# Fixed real-audio corpus. Keep `name` stable across baseline/after runs —
# it's the join key for comparison.
SOURCES = [
    Source(
        name="transcribe_moonlight_sonata",
        pipeline="transcribe",
        audio_path=ASSETS_DIR / "transcribe_moonlight_sonata.mp3",
        note=(
            "Real solo-piano recording (Beethoven Moonlight Sonata, 2nd mvt, "
            "public-domain repertoire; ~132s), downloaded fresh via yt-dlp "
            "through the real /transcribe youtube_url path when this asset was "
            "captured, then cached locally as an mp3 so re-runs don't depend on "
            "network/video availability. No genuine user-recorded solo piano "
            "audio was found in the repo/session cache, so this is the closest "
            "real substitute for Spec 1's target input."
        ),
    ),
    Source(
        name="arrange_song_A",
        pipeline="arrange",
        audio_path=ASSETS_DIR / "arrange_song_A.wav",
        note=(
            "Real 45s song mix, recovered from backend/storage (checksum "
            "eb3461c0...), re-uploaded there multiple times in a prior session "
            "under the generic title 'mix' while tuning Spec 2. Per project "
            "memory this is one of {Let It Be, Someone Like You, Fix You} from "
            "the 2026-09-02 spec2 spike, but the stored metadata only recorded "
            "the literal filename 'mix', not which song, and the exact mapping "
            "could not be recovered (a tempo-detection probe was inconclusive). "
            "Treated as an anonymous but genuine, previously-verified real song."
        ),
    ),
    Source(
        name="arrange_song_B",
        pipeline="arrange",
        audio_path=ASSETS_DIR / "arrange_song_B.wav",
        note="Same provenance as arrange_song_A (checksum 4b6ab62a...), different song.",
    ),
    Source(
        name="arrange_song_C",
        pipeline="arrange",
        audio_path=ASSETS_DIR / "arrange_song_C.wav",
        note="Same provenance as arrange_song_A (checksum 01b8c18f...), different song.",
    ),
    Source(
        name="arrange_instrumental_big_rock",
        pipeline="arrange",
        audio_path=ASSETS_DIR / "arrange_instrumental_big_rock.mp3",
        note=(
            "Real full-band rock instrumental (no vocals). This is the exact "
            "track whose real-audio verification during Track 3 Phase 1 "
            "found assign_hands's badly unbalanced hand split (RH 1169/LH 29 "
            "notes, 83% of RH bass-register) that this plan fixes -- kept in "
            "the fixed corpus going forward as this fix's regression check. "
            "Ultimately fixed not by changing assign_hands but by bypassing "
            "it for this path entirely, transcribing the bass/other stems "
            "separately instead of mixing them and hand-splitting the result."
        ),
    ),
    # The 5 MAESTRO test-split clips from the ground-truth eval (2a), reused
    # here to generate real Easy/Medium/Hard MusicXML for the difficulty-tier
    # human-judgment validation (2b) -- see clips.py in ground_truth_eval/
    # for the same 5 names/provenance.
    Source(
        name="maestro_scriabin_entragete",
        pipeline="transcribe",
        audio_path=MAESTRO_ASSETS_DIR / "scriabin_entragete.wav",
        note="MAESTRO v3.0.0 test-split clip (Scriabin, Entragete Op.63); see ground_truth_eval/clips.py.",
    ),
    Source(
        name="maestro_debussy_etude7",
        pipeline="transcribe",
        audio_path=MAESTRO_ASSETS_DIR / "debussy_etude7.wav",
        note="MAESTRO v3.0.0 test-split clip (Debussy, Etude No. 7); see ground_truth_eval/clips.py.",
    ),
    Source(
        name="maestro_scarlatti_k525",
        pipeline="transcribe",
        audio_path=MAESTRO_ASSETS_DIR / "scarlatti_k525.wav",
        note="MAESTRO v3.0.0 test-split clip (Scarlatti, Sonata K. 525); see ground_truth_eval/clips.py.",
    ),
    Source(
        name="maestro_liszt_gnomenreigen",
        pipeline="transcribe",
        audio_path=MAESTRO_ASSETS_DIR / "liszt_gnomenreigen.wav",
        note="MAESTRO v3.0.0 test-split clip (Liszt, Concert Etude \"Gnomenreigen\"); see ground_truth_eval/clips.py.",
    ),
    Source(
        name="maestro_schubert_impromptu90no4",
        pipeline="transcribe",
        audio_path=MAESTRO_ASSETS_DIR / "schubert_impromptu90no4.wav",
        note="MAESTRO v3.0.0 test-split clip (Schubert, Impromptu Op. 90 No. 4); see ground_truth_eval/clips.py.",
    ),
]


def run_one_source(base_url: str, source: Source, label: str) -> dict:
    print(f"[{source.name}] submitting to /{source.pipeline} ...", flush=True)
    result_entry = {
        "name": source.name,
        "pipeline": source.pipeline,
        "provenance_note": source.note,
        "status": "pending",
    }

    try:
        if source.pipeline == "transcribe":
            body = submit_transcribe(base_url, audio_path=source.audio_path, youtube_url=source.youtube_url)
        elif source.pipeline == "arrange":
            body = submit_arrange_and_wait(base_url, audio_path=source.audio_path, youtube_url=source.youtube_url)
            if body.get("status") == "failed":
                result_entry["status"] = "failed"
                result_entry["detail"] = body.get("detail")
                print(f"[{source.name}] FAILED: {body.get('detail')}")
                return result_entry
        else:
            raise ValueError(f"unknown pipeline {source.pipeline!r}")
    except Exception as exc:  # noqa: BLE001 - want to record any failure, keep going
        result_entry["status"] = "error"
        result_entry["detail"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        return result_entry

    song_id = body["song_id"]
    title = body.get("title", "")
    result_entry["song_id"] = song_id
    result_entry["title"] = title
    result_entry["tiers"] = {}

    song_out_dir = OUTPUT_DIR / label / source.name
    for tier in TIERS:
        musicxml_path = song_out_dir / f"{tier}.musicxml"
        fetch_musicxml(base_url, song_id, tier, musicxml_path)

        tier_metrics = analyze_musicxml(musicxml_path)

        midi_path = song_out_dir / f"{tier}.mid"
        export_midi(musicxml_path, midi_path)

        downloads_name = f"{source.name}-{tier}-{label}.mid"
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(midi_path, DOWNLOADS_DIR / downloads_name)

        tier_metrics["midi_path"] = str(midi_path)
        tier_metrics["downloads_copy"] = str(DOWNLOADS_DIR / downloads_name)
        result_entry["tiers"][tier] = tier_metrics
        print(f"[{source.name}] {tier}: "
              f"{sum(p['note_count'] for p in tier_metrics['parts'].values())} total notes -> "
              f"{downloads_name}")

    result_entry["status"] = "ok"
    return result_entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--label", required=True,
        help="Run label, e.g. 'baseline' or 'after-tempo-detection'. "
             "Used as the output subdirectory name and the Downloads filename suffix.",
    )
    parser.add_argument(
        "--only", default=None,
        help="Comma-separated subset of source names to run (default: all).",
    )
    args = parser.parse_args()

    sources = SOURCES
    if args.only:
        wanted = set(args.only.split(","))
        sources = [s for s in SOURCES if s.name in wanted]
        if not sources:
            print(f"No sources matched --only={args.only!r}. Known: {[s.name for s in SOURCES]}")
            return 1

    for s in sources:
        if s.audio_path is not None and not s.audio_path.exists():
            print(f"ERROR: asset missing for source {s.name!r}: {s.audio_path}")
            return 1

    print("Starting real backend (unmodified app.main:app) ...")
    handle = start_backend()
    print(f"Backend up at {handle.base_url}")

    results = []
    try:
        for source in sources:
            results.append(run_one_source(handle.base_url, source, args.label))
    finally:
        handle.stop()
        print("Backend stopped.")

    summary = {"label": args.label, "sources": results}
    metrics_path = OUTPUT_DIR / args.label / "metrics.json"
    save_json(summary, metrics_path)
    print(f"\nWrote combined metrics: {metrics_path}")
    print(f"MIDI files copied to: {DOWNLOADS_DIR}")

    n_ok = sum(1 for r in results if r["status"] == "ok")
    n_total = len(results)
    print(f"\n{n_ok}/{n_total} sources completed successfully.")
    return 0 if n_ok == n_total else 2


if __name__ == "__main__":
    raise SystemExit(main())
