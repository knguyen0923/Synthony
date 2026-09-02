# LH True Transcription Design

## Motivation

Spec 2's LH (left-hand piano accompaniment) has, until now, been synthesized: chord detection (`app/chords/detect.py`) matches a chord symbol per bar against chroma features, and `app/arrangement/{easy,medium,hard}.py` render those symbols as arbitrary patterns (a held root, a block triad, an Alberti-bass arpeggio). Earlier this session that generation was consolidated so all three tiers derive their tone choices from one function (`theory.lh_voicing()`) — but the underlying content was never *what the song's harmony instruments are actually playing*, just a music-theory guess at a chord label rendered through a fixed pattern.

RH (melody), by contrast, has always been a real transcription: Basic Pitch runs on the isolated vocals stem and produces actual detected notes. This design brings LH to parity — Hard mode becomes a genuine transcription of the song's harmonic/bass content, and Easy/Medium become mechanical simplifications of that one rich transcription, exactly like RH's Easy/Medium already are.

This replaces, rather than extends, the current chord-driven LH synthesis. The `app/arrangement/` package and most of `app/chords/` are retired as part of this work.

## Current State (for reference)

- `app/melody/extract.py`: `extract_melody_notes(audio_path)` runs `transcribe_audio_to_notes` (Basic Pitch) on the vocals stem, then `reduce_to_monophonic()` collapses overlapping detections to one line (keeping the higher-confidence note). `build_melody_part()` cleans up fragmented onsets via `quantize_melody(notes, CLEANUP_GRID=0.25, ...)` and returns the RH "Hard" base `stream.Part`.
- `app/difficulty/quantize.py`: `quantize_part(part, grid)` snaps note onsets to a grid, keeping only the first note per slot — used for RH's Easy/Medium.
- `app/difficulty/range_shift.py`: `shift_into_range(part, low, high)` octave-shifts every note into `[low, high]`, preserving pitch class — fully generic, hand-agnostic already.
- `app/difficulty/easy.py` / `medium.py`: define `EASY_GRID=1.0`/`MEDIUM_GRID=0.5`, `EASY_RH_RANGE`/`MEDIUM_RH_RANGE`, and — already present but currently only used by the Spec 1 `/transcribe` pipeline — `EASY_LH_RANGE=(36,48)` and `MEDIUM_LH_RANGE=(36,55)`.
- `app/arrangement/`: `easy.py`/`medium.py`/`hard.py` (chord-symbol → rendered LH Part, one pattern per tier), `theory.py` (chord math + the `lh_voicing()` consolidation from earlier today), `engine.py` (`generate_lh_variants`), `types.py` (`ChordSymbol`). All retired by this design.
- `app/chords/detect.py`: `detect_chords(audio_path) -> (chords, seconds_per_quarter, key)` — loads audio, computes chroma, detects key (`chords/key.py::detect_key`), beat-tracks for tempo, matches a chord per bar (`chords/match.py::match_chord`), merges/absorbs short blips. Only the chroma/key/tempo parts survive this design; bar-matching and `chords/match.py` are retired.
- `arrange_pipeline.py::_rh_variants(melody_notes, seconds_per_quarter)`: builds one rich RH base then derives Easy/Medium via `quantize_part` + `shift_into_range`. This is the shape LH now adopts too.

## New Architecture

```
mix.wav
  ├─ separate_stems() → vocals.wav, bass.wav, other.wav, drums.wav
  ├─ vocals.wav ──────────────────────────────────► extract_melody_notes() → build_melody_part()  [RH Hard base, unchanged]
  └─ mix_wav_files(bass.wav, other.wav) → harmony.wav
        ├─ detect_key_and_tempo(harmony.wav) → (key, seconds_per_quarter)
        └─ extract_lh_notes(harmony.wav) → build_lh_part()  [LH Hard base — NEW]

RH: Hard = base; Easy/Medium = shift_into_range(quantize_part(base, GRID, max_voices=1), *RANGE)   [unchanged]
LH: Hard = base; Easy/Medium = shift_into_range(quantize_part(base, GRID, max_voices=N), *RANGE)   [NEW — same shape]
```

Both hands now follow the identical pattern: one real transcription as the Hard base, Easy/Medium mechanically derived from it via the same `quantize_part`/`shift_into_range` pair. `quantize_part` gains an optional `max_voices` parameter (default `1`, so RH's existing call sites and behavior are untouched) that lets it also serve LH's polyphonic reduction.

## Components

### `app/lh/extract.py` (new, mirrors `app/melody/extract.py`)

```python
def cap_simultaneous_notes(notes: list[NoteEvent], max_voices: int) -> list[NoteEvent]:
    """Stream through notes in onset order, keeping at most max_voices
    concurrently 'held' notes. When a new note would exceed the cap,
    evict the lowest-velocity currently-held note before adding it.
    Generalizes melody.extract.reduce_to_monophonic's confidence-over-
    raw-detection principle from 1 voice to N — Basic Pitch on a busy
    'other' stem (piano/guitar/strings/synths, whatever Demucs didn't
    call vocals/drums/bass) can over-detect beyond what a hand can
    physically play; this caps to a plausible upper bound."""

def extract_lh_notes(audio_path: str, max_voices: int = HARD_MAX_VOICES) -> list[NoteEvent]:
    """Run Basic Pitch on harmony audio (bass+other mix) and cap to
    max_voices concurrent notes. Unlike RH, deliberately keeps polyphony
    — real LH accompaniment is chordal, not a single line."""

def build_lh_part(notes: list[NoteEvent], seconds_per_quarter: float = SECONDS_PER_QUARTER) -> stream.Part:
    """Register-shift the capped transcription into HARD_LH_RANGE and
    build the LH 'Hard' Part — the full-detail base every tier derives
    from, same role as melody.extract.build_melody_part for RH."""
```

`HARD_MAX_VOICES` starts at `4` (a tuning constant, expect to adjust after listening — see Tuning below). `HARD_LH_RANGE` starts at `(36, 55)`, the current Hard-tier range.

No onset-cleanup/legato pass (RH's `quantize_melody`/`CLEANUP_GRID` equivalent) in the first version — that logic assumes a single line with gaps to close, which doesn't map cleanly onto genuine overlapping polyphony. If real-song listening surfaces fragmented/broken-sounding onsets, add a targeted cleanup pass then rather than guessing at one now.

### `app/difficulty/quantize.py` (modified)

`quantize_part(part: stream.Part, grid: float, max_voices: int = 1) -> stream.Part`: group notes by grid slot; within each slot, keep the top `max_voices` distinct-pitch-class notes by velocity (same dedup-by-pitch-class + cap pattern `app/difficulty/medium.py::_reduce_to_voicing` already uses for Spec 1's LH). `max_voices=1` (the default, and RH's only call site) must produce byte-identical output to today's function — this is the regression contract a test locks in.

### `app/chords/detect.py` (trimmed)

`detect_key_and_tempo(audio_path: str) -> tuple[tuple[int, str], float]`: keeps chroma computation, `detect_key`, and beat-tracking (still needed for tempo/`seconds_per_quarter`); drops bar-splitting, `match_chord`, and all merge/absorb logic. Returns `(key, seconds_per_quarter)`.

### `arrange_pipeline.py` (modified)

```python
def _lh_variants(harmony_path: str, seconds_per_quarter: float = SECONDS_PER_QUARTER):
    notes = extract_lh_notes(harmony_path)
    if not notes:
        raise ValueError("No harmonic content detected")
    base = build_lh_part(notes, seconds_per_quarter)
    return {
        "easy": shift_into_range(quantize_part(base, EASY_GRID, max_voices=1), *EASY_LH_RANGE),
        "medium": shift_into_range(quantize_part(base, MEDIUM_GRID, max_voices=3), *MEDIUM_LH_RANGE),
        "hard": base,
    }
```

Reuses `EASY_GRID`/`MEDIUM_GRID` and `EASY_LH_RANGE`/`MEDIUM_LH_RANGE` already defined in `app/difficulty/easy.py`/`medium.py` (the latter two currently only used by the Spec 1 `/transcribe` pipeline) — no new duplicate constants. `run_arrange_pipeline` calls `detect_key_and_tempo(harmony_path)` instead of `detect_chords`, and `_lh_variants(harmony_path, seconds_per_quarter)` instead of `generate_lh_variants(chords, seconds_per_quarter)`.

## Retired

- `app/arrangement/` in full: `easy.py`, `medium.py`, `hard.py`, `engine.py`, `theory.py`, `types.py`.
- `app/chords/match.py` and its tests.
- `backend/tests/test_arrangement_*.py` (all of them) and any chord-matching tests in `backend/tests/test_chords_*.py` that only exercise the retired matching path.
- `app/chords/key.py` survives unchanged (still used by `detect_key_and_tempo`).

## Testing

TDD as always. New coverage needed:
- `cap_simultaneous_notes`: no-overlap passthrough, over-cap eviction picks lowest velocity, ties/edge cases at exactly `max_voices`.
- `extract_lh_notes` / `build_lh_part`: same mocking approach the existing melody tests presumably use for `transcribe_audio_to_notes`.
- `quantize_part`'s new `max_voices` parameter: multi-voice slot capping and dedup-by-pitch-class, **plus** an explicit regression test that `max_voices=1` output is unchanged from before this change (run existing RH-facing tests unmodified as the primary evidence).
- `detect_key_and_tempo`: key/tempo detection behavior carried over from the relevant existing `test_chords_detect.py` cases (adapted for the new two-tuple return and dropped chord list).
- `arrange_pipeline`'s `_lh_variants` and the end-to-end `/arrange` flow.

Real-audio verification (the 3 cached songs → MIDI → listen) is mandatory before calling this done, same as always — and more load-bearing than usual here, since this is the first time this pipeline's *quality* depends on Basic Pitch's actual output on a Demucs "other" stem, which hasn't been specifically evaluated before (chord detection tolerated noisy chroma; note-level transcription may not).

## Tuning parameters to expect adjusting by ear

- `HARD_MAX_VOICES` (starting at 4)
- Medium's voice cap (starting at 3, matching today's `MAX_BLOCK_TONES`)
- `HARD_LH_RANGE`, `EASY_LH_RANGE`, `MEDIUM_LH_RANGE` (starting at today's values)
- Whether an onset-cleanup pass turns out to be needed after all

## Open risk

Demucs's "other" stem is a catch-all (piano, guitar, strings, synths, anything that isn't vocals/drums/bass) — for songs where "other" contains more than one instrument playing simultaneously, the transcription will pick up all of it as if it were one LH part, with no way to distinguish "the piano's chords" from "the string pad" from "the guitar riff." This is a real quality ceiling, not a bug to fix in this pass — worth knowing going in, and worth listening for specifically during verification.
