#!/usr/bin/env python3
"""Diff two metrics.json files produced by run_baseline.py (e.g. baseline
vs. after) and print a compact before/after table per source/tier/part.

Usage:
  python diff_metrics.py output/baseline/metrics.json output/after-X/metrics.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: str) -> dict:
    data = json.loads(Path(path).read_text())
    return {s["name"]: s for s in data["sources"]}


def fmt_delta(old, new):
    if old is None or new is None:
        return "n/a"
    delta = new - old
    sign = "+" if delta > 0 else ""
    return f"{old} -> {new} ({sign}{delta})"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1

    before = load(sys.argv[1])
    after = load(sys.argv[2])

    all_names = sorted(set(before) | set(after))
    for name in all_names:
        b = before.get(name)
        a = after.get(name)
        print(f"\n=== {name} ===")
        if b is None:
            print("  (new in 'after' run)")
        if a is None:
            print("  (missing from 'after' run)")
        if b is None or a is None:
            continue
        if b["status"] != "ok" or a["status"] != "ok":
            print(f"  status: {b['status']} -> {a['status']}")
            continue

        for tier in ("easy", "medium", "hard"):
            bt = b.get("tiers", {}).get(tier)
            at = a.get("tiers", {}).get(tier)
            if not bt or not at:
                continue
            print(f"  [{tier}]")
            part_names = sorted(set(bt["parts"]) | set(at["parts"]))
            for part in part_names:
                bp = bt["parts"].get(part, {})
                ap = at["parts"].get(part, {})
                note_delta = fmt_delta(bp.get("note_count"), ap.get("note_count"))
                bpeak = bp.get("voice_count", {}).get("peak_simultaneous_voices")
                apeak = ap.get("voice_count", {}).get("peak_simultaneous_voices")
                peak_delta = fmt_delta(bpeak, apeak)
                brange = bp.get("pitch_range") or {}
                arange = ap.get("pitch_range") or {}
                print(f"    {part}: notes {note_delta}; peak_voices {peak_delta}; "
                      f"range {brange.get('min_name')}-{brange.get('max_name')} -> "
                      f"{arange.get('min_name')}-{arange.get('max_name')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
