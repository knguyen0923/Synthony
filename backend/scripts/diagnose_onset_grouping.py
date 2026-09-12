#!/usr/bin/env python3
"""One-time diagnostic: measure whether onset-grouping tolerance
(ONSET_ROUND_DECIMALS in app.notation.hand_assignment) is a material
contributor to assign_hands's lone-note-onset rate on real multi-instrument
input, or whether that rate is simply genuine (bass/chord tones landing on
truly distinct onsets). See docs/superpowers/specs/
2026-09-12-hand-split-instrumental-fix-design.md's "Diagnostic" section.

Reproduces exactly what app.arrange_pipeline._instrumental_variants does to
get from a raw audio file to the note list assign_hands receives (stem
separation -> bass+other mix -> transcription), then measures onset-group
sizes and near-miss merges on that note list. Does not call assign_hands
itself -- this only inspects _group_by_onset's output.

USAGE
  cd backend
  ./.venv/bin/python scripts/diagnose_onset_grouping.py \
      scripts/quality_harness/assets/arrange_instrumental_big_rock.mp3
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.arrange_pipeline import mix_wav_files  # noqa: E402
from app.lh.extract import LH_MINIMUM_NOTE_LENGTH_MS  # noqa: E402
from app.notation.hand_assignment import _group_by_onset  # noqa: E402
from app.separation.separator import separate_stems  # noqa: E402
from app.transcription.audio_to_midi import transcribe_audio_to_notes  # noqa: E402

# A near-miss merge window: two onsets this close together are the kind of
# timing jitter Basic Pitch/Demucs could plausibly produce for notes meant
# to sound together, distinct from a genuinely separate musical event.
# 30ms is comfortably larger than typical onset-detection jitter and
# comfortably smaller than the shortest notes this pipeline's minimum note
# length (180ms) would ever produce.
MERGE_WINDOW_SECONDS = 0.03

# Below this fraction of lone-note onsets being near-miss-mergeable, onset
# grouping is ruled out as a material contributor (the observed lone-note
# rate is mostly genuine, not a grouping artifact).
MATERIAL_THRESHOLD = 0.15


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <audio_path>")
        return 1
    audio_path = sys.argv[1]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        print(f"Separating stems for {audio_path} ...")
        stems = separate_stems(audio_path, tmp_dir / "stems")
        harmony_path = mix_wav_files(stems.bass, stems.other, tmp_dir / "harmony.wav")

        print("Transcribing harmony mix ...")
        notes = transcribe_audio_to_notes(str(harmony_path), minimum_note_length=LH_MINIMUM_NOTE_LENGTH_MS)

    groups = _group_by_onset(notes)
    total_groups = len(groups)
    size_1_groups = [(i, g) for i, g in enumerate(groups) if len(g) == 1]

    mergeable = 0
    for i, group in size_1_groups:
        if i + 1 >= len(groups):
            continue
        next_group = groups[i + 1]
        this_onset = group[0].start
        next_onset = next_group[0].start
        if next_onset - this_onset <= MERGE_WINDOW_SECONDS:
            mergeable += 1

    fraction_size_1 = len(size_1_groups) / total_groups if total_groups else 0.0
    fraction_mergeable = mergeable / len(size_1_groups) if size_1_groups else 0.0

    print(f"Total onset groups: {total_groups}")
    print(f"Size-1 (lone-note) groups: {len(size_1_groups)} ({fraction_size_1:.1%} of all groups)")
    print(f"Of those, within {MERGE_WINDOW_SECONDS * 1000:.0f}ms of the next onset: "
          f"{mergeable} ({fraction_mergeable:.1%} of size-1 groups)")

    if fraction_mergeable >= MATERIAL_THRESHOLD:
        print(f"MATERIAL (>= {MATERIAL_THRESHOLD:.0%}): onset-grouping tolerance is a real contributor. "
              "Implement the ONSET_MERGE_WINDOW_SECONDS follow-up described in Task 1's Step 3 "
              "before proceeding to Task 2.")
    else:
        print(f"RULED OUT (< {MATERIAL_THRESHOLD:.0%}): the lone-note rate is mostly genuine, "
              "not a grouping artifact. Proceed directly to Task 2; no change to _group_by_onset needed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
