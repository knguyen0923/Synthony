# MAESTRO ground-truth transcription eval — design

## Context

Part of the 2026-09-16 portfolio-review Improvement Backlog (recorded in
`RESUME.md`'s "Queued" section), Priority 2a — the highest-priority item.
Big Rock's tempo investigation is shelved for now per explicit user
decision (root cause confirmed, drums-stem fix kept but doesn't resolve
it, onset-midpoint heuristic designed but not built — see `RESUME.md`).

The existing quality harness (`backend/scripts/quality_harness/`) diffs
objective metrics (note count, voice count, pitch range, duration
histogram) run-over-run — useful for catching regressions, but it never
checks correctness against a known-right answer. This spec adds that:
pull a handful of MAESTRO dataset clips (piano recordings paired with
ground-truth MIDI — the same dataset `piano_transcription_inference` was
trained on), run them through Spec 1's solo-piano transcription function,
and compute real note-level precision/recall/F1 against the ground truth.

This is the first of 5 backlog sub-projects being brainstormed in
priority order (2a → 2b → 3a → 3b → 4); 2b (difficulty-tier validation)
depends on this one existing.

## Scope

**In scope**: a standalone eval script that measures raw transcription
accuracy of `transcribe_piano_audio_to_notes()` against MAESTRO ground
truth, reporting precision/recall/F1. Report-only — no pass/fail gate,
no CI wiring.

**Out of scope**: the full HTTP `/transcribe` pipeline or any difficulty
tier (their transforms would show up as "errors" against ground truth
even though they're intentional); wiring this into CI or the existing
`quality_harness/` run-over-run diffing; anything about difficulty-tier
validation (that's 2b, next).

## Architecture

A new sibling directory to `backend/scripts/quality_harness/`, since this
is a genuinely different concern (absolute correctness vs. run-over-run
diffing):

```
backend/scripts/ground_truth_eval/
  assets/                  # gitignored, 5 MAESTRO (audio, MIDI) pairs
  fetch_maestro_clips.py   # one-time downloader
  metrics.py               # mir_eval wrapper: NoteEvent + pretty_midi -> P/R/F1
  eval.py                  # CLI: runs transcription, scores, reports
  output/                  # gitignored, <label>/results.json per run
```

### `fetch_maestro_clips.py`

One-time setup script. Downloads 5 (audio, MIDI) pairs from MAESTRO's
official **test** split (not train) — a legitimate held-out eval, not
data the model may have been tuned against. Spans a couple of composers
and tempos for variety. Exact download URLs/manifest to be verified live
against MAESTRO's public hosting at implementation time (not hardcoded
from memory in this spec). Downloaded files land in `assets/`, which is
added to `.gitignore` (same pattern as `quality_harness/assets/` — binary
audio/MIDI fixtures don't belong in git history).

### `metrics.py`

Wraps `mir_eval.transcription.precision_recall_f1_overlap`:

- Input: a list of predicted `NoteEvent` (start, end, pitch, velocity —
  the existing dataclass in `app/notation/types.py`) and a ground-truth
  `pretty_midi.PrettyMIDI` object.
- Converts both to mir_eval's expected shape: `(N, 2)` onset/offset
  interval arrays in seconds, plus a parallel pitch array in **Hz**
  (mir_eval takes frequency, not MIDI note number — convert via
  `librosa.midi_to_hz`).
- Calls `precision_recall_f1_overlap(ref_intervals, ref_pitches,
  est_intervals, est_pitches, onset_tolerance=0.05, pitch_tolerance=50,
  offset_ratio=None)` — 50ms onset tolerance, exact-ish pitch match (50
  cents = quarter-tone, effectively "same MIDI pitch"), offset ignored
  (matches the backlog's "onset + pitch match" ask; duration/offset
  accuracy isn't part of this eval).
- Returns a plain dict: `{precision, recall, f1, n_predicted, n_ground_truth}`.

### `eval.py`

CLI, one positional/flag for a run `--label` (same convention as
`run_baseline.py`). For each of the 5 clips:

1. Call `transcribe_piano_audio_to_notes(audio_path)` directly (no HTTP,
   no difficulty tiers — raw Spec 1 transcription accuracy only, per
   explicit decision) to get predicted notes.
2. Load the paired ground-truth MIDI via `pretty_midi.PrettyMIDI(midi_path)`.
3. Score via `metrics.py`, print a per-clip precision/recall/F1 line.
4. Aggregate: micro-average across all notes from all clips (not a
   macro-average of per-clip F1s — a clip with more notes should weigh
   proportionally more).
5. Write `output/<label>/results.json` (per-clip + aggregate numbers,
   provenance of which clips were used) for later before/after
   comparison, mirroring `quality_harness/`'s labeled-output convention.

No pass/fail threshold, no non-zero exit on low scores — this is a
reporting tool for a human to read and judge, same spirit as the existing
harness (which a human diffs, not CI).

## New dependency

`mir_eval` added to `backend/requirements.txt` — the standard MIR
research library (used by the MAESTRO paper and Onsets & Frames) for
onset+pitch note-transcription matching. Avoids reinventing greedy
note-matching/assignment logic.

## Testing

TDD on `metrics.py`'s matching wrapper using small synthetic note lists
constructed by hand (known precision/recall by construction — e.g. a
list with one dropped note, one extra note, one pitch error, one onset
just inside/outside the 50ms tolerance) — fast, deterministic, no audio
or model involved. `eval.py` and `fetch_maestro_clips.py` stay untested
orchestration scripts, same as `run_baseline.py` today (not part of the
`backend/tests/` pytest suite).

## Open questions for implementation time

- Exact MAESTRO test-split clip selection and download mechanism (URLs
  to be verified live, not assumed).
