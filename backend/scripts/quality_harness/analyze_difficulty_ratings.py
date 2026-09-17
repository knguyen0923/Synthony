#!/usr/bin/env python3
"""Reads filled-in difficulty_ratings_template.json (backlog item 2b:
validate the rule-based difficulty tiers against real human sight-reading
judgment) and reports, per piece, whether Easy/Medium/Hard scores actually
increase in that order, plus per-tier aggregate stats across pieces.

Report-only: no pass/fail gate, no verdict about whether a learned
difficulty model is worth building -- that decision is the human's to
make after reading this output, same spirit as the ground-truth eval
(backend/scripts/ground_truth_eval/eval.py).

USAGE
  cd backend/scripts/quality_harness
  cp difficulty_ratings_template.json my_ratings.json
  # ... fill in each "score" field by hand after viewing the .musicxml ...
  ../../.venv/bin/python analyze_difficulty_ratings.py my_ratings.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TIER_ORDER = ("easy", "medium", "hard")


def analyze_ratings(ratings: list[dict]) -> dict:
    by_name: dict[str, dict[str, float]] = {}
    for entry in ratings:
        by_name.setdefault(entry["name"], {})[entry["tier"]] = entry["score"]

    complete = {
        name: tiers for name, tiers in by_name.items()
        if all(tiers.get(t) is not None for t in TIER_ORDER)
    }
    n_incomplete = len(by_name) - len(complete)

    violations = []
    ties = []
    for name, tiers in complete.items():
        for lo, hi in zip(TIER_ORDER, TIER_ORDER[1:]):
            if tiers[hi] < tiers[lo]:
                violations.append({
                    "name": name,
                    "detail": f"{hi} ({tiers[hi]}) scored lower than {lo} ({tiers[lo]})",
                })
            elif tiers[hi] == tiers[lo]:
                ties.append({
                    "name": name,
                    "detail": f"{hi} and {lo} tied at {tiers[hi]}",
                })

    tier_stats = {}
    for tier in TIER_ORDER:
        scores = [tiers[tier] for tiers in complete.values()]
        if scores:
            tier_stats[tier] = {
                "mean": sum(scores) / len(scores),
                "min": min(scores),
                "max": max(scores),
            }

    return {
        "n_pieces_rated": len(complete),
        "n_pieces_incomplete": n_incomplete,
        "violations": violations,
        "ties": ties,
        "all_monotonic": len(violations) == 0,
        "tier_stats": tier_stats,
    }


def _print_report(result: dict) -> None:
    print(f"{result['n_pieces_rated']} piece(s) fully rated, {result['n_pieces_incomplete']} incomplete (skipped).")
    for tier in TIER_ORDER:
        stats = result["tier_stats"].get(tier)
        if stats:
            print(f"  {tier}: mean={stats['mean']:.1f} min={stats['min']} max={stats['max']}")
    if result["all_monotonic"]:
        print("\nAll rated pieces have Easy <= Medium <= Hard perceived difficulty.")
    else:
        print(f"\n{len(result['violations'])} ordering violation(s):")
        for v in result["violations"]:
            print(f"  {v['name']}: {v['detail']}")
    if result["ties"]:
        print(f"\n{len(result['ties'])} tier tie(s) (not violations, but worth a look):")
        for t in result["ties"]:
            print(f"  {t['name']}: {t['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ratings_path", type=Path, help="Path to a filled-in ratings JSON file.")
    args = parser.parse_args()

    data = json.loads(args.ratings_path.read_text())
    result = analyze_ratings(data["ratings"])
    _print_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
