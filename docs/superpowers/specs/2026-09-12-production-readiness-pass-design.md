# Production-Readiness Pass — Design

## Context

Synthony's two transcription/arrangement pipelines are complete and
real-audio verified (see `TAKEAWAYS.md`). The user asked for a
"production ready" pass. Scoping question: what does that mean for a
project that is explicitly **local-only, single-user, single-machine**,
with no plans to deploy it anywhere public? Answer, confirmed with the
user:

- Deployment target: **local-only** — no public/always-on hosting, no
  auth, no multi-tenant concerns (unchanged from the existing Tier 1
  scope note).
- Usage pattern: **one person, one machine at a time** — no concurrent
  multi-client access to design around.
- "Hardening" means, in priority order the user picked: storage/disk
  management, startup/operational robustness, easier setup, and a
  closing audit sweep for anything else that would annoy a normal user
  running this locally.

This is a bug-fix/polish pass, not a new feature — same spirit as the
2026-09-12 Tier 1 bug-fix plan, scoped to operational rough edges rather
than pipeline-quality bugs.

## What already exists (don't duplicate)

- `evict_oldest_songs()` (`backend/app/storage.py:49`) already caps
  total stored songs at `MAX_STORED_SONGS` (100), called after both
  `/transcribe` and `/arrange` complete. This is a coarse, whole-song,
  count-based cap — it does not address dead files *inside* a still-kept
  song's directory.
- `GET /health` (`backend/app/main.py:130`) already exists but always
  returns `{"status": "ok"}` unconditionally — no actual checks.
- `configure_logging()` (`backend/app/logging_config.py`) already wires
  up `LOG_LEVEL`-controlled stdout logging via `logging.basicConfig`.
  There is no file handler and no rotation.
- `backend/app/ingestion/youtube.py` already raises a clear
  `IngestionError` message if `ffmpeg` postprocessing fails — but only
  when a YouTube/Spotify request is actually made, not at startup.

## Section 1: Storage/disk management — stem cleanup

**Problem:** `run_arrange_pipeline` (`backend/app/arrange_pipeline.py`)
writes Demucs's separated stems to `dest_dir/stems/` (`vocals.wav`,
`drums.wav`, `bass.wav`, `other.wav`) via `separate_stems`, and (for the
vocal-melody path) an additional mixed `stems/harmony.wav`. Once the
pipeline finishes and the 3 MusicXML files are exported, none of these
WAV files are ever read again — but nothing deletes them. Raw,
uncompressed stem WAVs are large (roughly the length of the source
audio, ×4 stems); across the 100-song cap this is potentially several
GB of dead weight that the existing count-based eviction doesn't touch
mid-song.

**Fix:** after `run_arrange_pipeline` reaches a terminal state (success
*or* failure — a failed job's partial stems are equally dead), delete
`dest_dir / "stems"` via `shutil.rmtree(..., ignore_errors=True)`. Keep
the original source audio (small by comparison, and useful if the user
ever wants to reprocess) and the exported MusicXML files.

**Where:** a `finally`-style cleanup in `run_arrange_pipeline`'s outer
try/except (the same function that already calls `evict_oldest_songs()`
on success) — must run on both the success path and the existing
generic-exception failure path, so a failed job doesn't leak its stems
forever either.

**Out of scope:** `/transcribe`'s solo-piano path doesn't create
separated stems at all (one model runs directly on the source audio),
so there's nothing to clean up there. A size-based (rather than
count-based) eviction cap is a bigger design (needs a size-accounting
strategy) and isn't needed once stems are cleaned up — the remaining
per-song footprint (source audio + 3 small MusicXML files) is modest
enough that the existing 100-song count cap is sufficient. Not pursuing
a size-based cap in this pass.

## Section 2: Startup/operational robustness

**Health check:** extend `GET /health` to actually report on the two
things that are silently required for full functionality but not
checked anywhere today:
- `ffmpeg` on `PATH` (via `shutil.which("ffmpeg")`) — required for
  YouTube/Spotify ingestion, not for file upload.
- The piano-transcription model checkpoint directory
  (`~/piano_transcription_inference_data/`) already existing — if
  absent, the *first* `/transcribe` request will trigger a ~170MB
  download, which is expected behavior, not a bug, but worth surfacing
  as an informational flag rather than a silent surprise.

Response shape (still `200` in all cases — these are informational, not
failures, since the app is still partially usable either way):

```json
{
  "status": "ok",
  "ffmpeg_available": true,
  "piano_model_downloaded": false
}
```

**Startup logging:** at process startup (in `main.py`, alongside
`configure_logging()`), log a `WARNING` if `ffmpeg` is missing, so it's
visible in the terminal immediately on boot instead of only surfacing
when a YouTube/Spotify request eventually fails. This does not block
startup — file-upload transcription works fine without `ffmpeg`.

**Log persistence:** add a `RotatingFileHandler` (stdlib
`logging.handlers`, e.g. 5MB × 3 backups) writing to `backend/logs/app.log`,
alongside the existing stdout stream handler `basicConfig` already sets
up. Purpose: if the server is ever run backgrounded (`nohup`, a
background terminal tab), there's a persisted trail to check after a
crash instead of only whatever scrollback the terminal still has. Kept
separate from `backend/storage/` (which holds only song data that
`list_songs()`/`evict_oldest_songs()` iterate over as directories) so log
files can never be mistaken for song directories. `backend/logs/` is
new — add it to `.gitignore` alongside the existing `backend/storage/`
entry.

## Section 3: Easier to run — `backend/setup.sh`

**Problem:** the README's backend setup section is five sequential
manual steps, one of which (the `numpy`/`scipy`/`cython`/`mido`
pre-install before `pip install --no-build-isolation -r
requirements.txt`) exists only because of a documented, easy-to-get-wrong
`madmom` build quirk — a copy-paste error here fails obscurely deep in
a `pip install`, not with a clear message.

**Fix:** `backend/setup.sh` — a small shell script that runs the exact
sequence already documented in the README (venv creation, pip upgrade,
the pinned pre-install line, then the `--no-build-isolation` install),
with `set -euo pipefail` so it stops cleanly on the first failure rather
than plowing ahead with a broken environment. The README's manual steps
stay as documented fallback/reference (useful if someone wants to see
what the script does, or hit a platform where it doesn't work
unmodified) but get a note pointing at the script as the normal path.

**Out of scope:** a single top-level script covering both
backend-venv-setup *and* frontend `npm install` — keeping it
backend-only matches the fact that the tricky, error-prone part
(madmom's build) is entirely backend-side; `npm install` has no
equivalent gotcha worth scripting around.

## Section 4: Closing audit sweep

After Sections 1–3 are implemented and tested, run a discovery sweep
(matching the process the Tier 1 bug-fix pass used) scoped to: **would
this annoy someone running Synthony locally for the first time, or
running it for the hundredth time?** Concretely check, at minimum:
- `cd frontend && npm run build && npm run preview` actually works
  end-to-end (this path isn't covered by `npm test`).
- `docker compose build && docker compose up` still works end-to-end
  (last verified during the prior hardening pass; confirm it's still
  true after this pass's changes).
- README accuracy — re-read it against the actual current setup steps
  (especially once `setup.sh` exists) and fix anything stale.
- Frontend-surfaced error messages (the ones hardened in the Tier 1
  pass) actually read clearly to a first-time user, not just
  technically-correct.

Findings from this sweep get fixed in the same pass if small (matching
the Tier 1 pass's own precedent), or explicitly logged as deferred if
not, rather than expanding into a new open-ended investigation.

## Testing

- Section 1: a test that runs `run_arrange_pipeline` against fake/mock
  stem-separation output and asserts `dest_dir / "stems"` no longer
  exists afterward, for both a success and a forced-failure case.
- Section 2: tests for `/health`'s new fields under both
  `ffmpeg`-present and `ffmpeg`-absent conditions (monkeypatching
  `shutil.which`), and under both piano-model-checkpoint-present and
  -absent conditions (monkeypatching the checkpoint path check).
- Section 3: `setup.sh` is a shell script — verified by actually running
  it in a clean venv during implementation (not a unit test), matching
  how the existing manual steps were verified when first documented.
- Section 4: no new automated tests by definition (it's an audit of
  existing behavior) — findings get their own targeted tests as part of
  their fix, same as any other bug fix.

## Non-goals

- No public/internet-facing deployment, no auth, no multi-tenant
  concerns — unchanged, explicit scope cut per the user's own
  confirmation above.
- No size-based storage eviction cap (see Section 1's "out of scope").
- No change to `/transcribe`'s synchronous, blocking-the-event-loop
  behavior — that's a separate, already-identified, lower-priority item
  tracked in `TAKEAWAYS.md`'s "What's next," not part of this pass.
