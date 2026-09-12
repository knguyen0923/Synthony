# Resuming Synthony

A concrete list of what's left, as of 2026-09-11. Production hardening
(CI, logging, a concurrency guardrail, Docker) is merged to `main` — this
is what to pick up next, roughly in priority order.

## Do these first (small, concrete, already scoped)

1. **Push `main` and watch the first real CI run.** `.github/workflows/ci.yml`
   was written and locally sanity-checked (backend suite, frontend lint)
   but has never actually executed on GitHub Actions — that's the one
   thing about it that can't be verified without a real push. Push, then
   check the Actions tab; the backend job's first run will also be its
   first real test of the model/pip caching, since nothing has primed
   those caches yet.
2. **Fix the docker-compose Spotify-credentials bug.** `backend/.env`
   (`SPOTIFY_CLIENT_ID`/`SPOTIFY_CLIENT_SECRET`/`MAX_CONCURRENT_JOBS`/`LOG_LEVEL`)
   doesn't actually reach the backend container today: `docker-compose.yml`'s
   `environment:` block silently overrides its own `env_file:` directive
   for every key both specify (Compose's precedence rules — `environment:`
   always wins). Fix: drop those four keys from the `environment:` block
   so `env_file` actually supplies them (or otherwise resolve the
   shadowing). Verify with `docker compose config` against a real
   `backend/.env` — that's how the bug was originally caught, and it's a
   config file, not a build, so no slow Docker build is needed to check it.
   Only affects Docker-based Spotify-link input; file upload and
   YouTube-link work fine either way.

## Bigger, needs its own scoping pass

3. **Decide on native arm64 Docker builds.** The backend image currently
   only builds natively on `linux/amd64` — a `demucs` transitive
   dependency (`sphn`) ships no `linux/aarch64` wheel, which matters since
   this repo's own dev machine is Apple Silicon. Documented with a
   `--platform linux/amd64` emulation workaround in `backend/Dockerfile`,
   not fixed. A real fix would add a Rust/maturin toolchain so `sphn`
   builds from source on arm64 — untested, and the one attempt at a
   related emulated build took 20+ minutes without finishing, so budget
   real time if you want to pursue this.
4. **Track 3 — broadening past pop/rock** (instrumentals, rap, orchestral,
   multi-melody songs). Explicitly deferred since Spec 2's design doc —
   this needs its own brainstorm/spec pass before any code, the same way
   Spec 2 itself got a Phase 0 spike before implementation. Not scoped
   yet; don't start writing a plan for this without that step first.

## Optional, lower priority

- `/transcribe` still runs its full ML pipeline synchronously on the
  event loop (pre-existing, not introduced by the hardening pass) — means
  two concurrent `/transcribe` requests can never contend for the new
  concurrency guardrail's job slots; the 503-when-busy path is only
  practically reachable via `/arrange`. Worth revisiting only if
  `/transcribe` needs genuine concurrent-request handling someday.
- A handful of Minor findings from the hardening pass's final review were
  deliberately left as-is (all confirmed low-risk, not bugs): mid-file
  `import` statements in two test files (matches this codebase's existing
  scattered-import style), no pre-hardening warning-count baseline was
  captured, ingestion (yt-dlp/ffmpeg) in `/transcribe` runs before the
  concurrency slot is probed so a rejected request still pays the
  download cost, and the backend Docker image runs as root (fine for a
  local-only image, just noting it was a conscious non-fix).
- Two long-standing, deliberately-parked items from before the hardening
  pass: distinguishing multiple simultaneous instruments within Demucs's
  catch-all "other" stem (a real quality ceiling, no clean fix available),
  and further LH onset-cleanup work (on hold unless listening actually
  surfaces fragmented onsets as a problem).

## Where to look for more context

- `TAKEAWAYS.md` — the full retrospective, including *why* several of the
  above were decided the way they were.
- `docs/superpowers/specs/2026-09-11-production-hardening-design.md` and
  `docs/superpowers/plans/2026-09-11-production-hardening.md` — the spec
  and implementation plan the hardening pass followed.
- `docs/superpowers/specs/2026-09-01-any-song-arrangement-design.md` — has
  the original "Phase 6 (later, separate spec) — Broaden beyond pop/rock"
  note that item 4 above picks up.
