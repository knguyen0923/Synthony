# Synthony — Production Hardening (personal/demo scope)

## Context

Spec 1 (solo-piano transcription) and Spec 2 (any-song arrangement) are
both feature-complete and ear-verified as of 2026-09-11 — see
`docs/superpowers/plans/` and `docs/superpowers/specs/` for the pipeline
work itself. What's never been addressed is the *engineering* hygiene
around that pipeline: there's no CI, no logging beyond bare
`try`/`except`, no guard against launching more concurrent heavy ML jobs
than one machine can actually run, and no easy-run story (Docker or
otherwise) for anyone other than the original developer with a
hand-built `.venv`.

The user has explicitly confirmed Synthony's scope for now: **"a personal
project just to demonstrate and learn skills."** Not public-facing, not
multi-tenant, not expected to survive hostile traffic. That statement is
this spec's central constraint — it rules out a whole category of
"production readiness" work (auth, rate limiting, a distributed job
queue) that would otherwise be assumed for a public service, and instead
aims at what actually matters for a personal project meant to demonstrate
engineering skill: it should have CI, it should log what it's doing, it
should be resistant to a developer accidentally overloading their own
machine, and it should be easy for someone else to spin up and evaluate.

## Goals

- CI (GitHub Actions) runs the existing backend `pytest` suite and a
  frontend build/lint check on every push, so regressions are caught
  automatically instead of relying on the developer remembering to run
  tests locally.
- Replace bare `except Exception:` blocks with real structured logging,
  so failures are diagnosable from logs instead of only from a stack
  trace at the point of failure.
- Add a concurrency guardrail so a burst of `/transcribe`/`/arrange`
  requests can't launch unbounded simultaneous Demucs/Basic
  Pitch/madmom/piano-transcription jobs and exhaust the host machine.
- A Dockerfile (or docker-compose) so the app can be built and run
  without hand-following the README's manual `.venv`/`pip
  install --no-build-isolation` recipe every time.

## Non-Goals (Out of Scope, per the personal/demo-project confirmation)

- Authentication or authorization of any kind.
- Rate limiting beyond the simple concurrency cap above (no per-IP
  quotas, no API keys).
- A persistent or distributed job queue (Celery/Redis or equivalent) —
  the existing in-memory `app/jobs.py` store stays in-memory; this
  matches `storage.py`'s existing "simplest thing that works for
  personal use" precedent (its own comment already calls out its
  100-song cap as a "personal-use history cap").
- Actually deploying anywhere. Per organization policy, nothing in this
  work writes to a production/live environment — the Docker/compose
  output here is for local use, not a hosting decision.
- Multi-process/multi-worker deployment (`uvicorn --workers N`) — the
  concurrency guardrail assumes a single process, same as the existing
  in-memory job store already does.

## Architecture

No changes to the transcription/arrangement pipeline itself. Four
additive, independent pieces layered on top of the existing FastAPI app:

```
.github/workflows/ci.yml     — backend pytest + frontend build/lint, on push
app/logging_config.py        — logging setup, wired in at app startup
app/concurrency.py           — job-slot semaphore, wraps the heavy-compute
                                sections of /transcribe and run_arrange_pipeline
backend/Dockerfile           — installs the README's exact dependency recipe
frontend/Dockerfile          — multi-stage build + static serve
docker-compose.yml           — wires both together for local `docker compose up`
```

Each piece is independently useful and independently testable — CI
doesn't depend on logging, logging doesn't depend on the concurrency
guardrail, and Docker packages the other three without changing them.

## Testing Strategy

- CI workflow: validated by triggering it (a real push) rather than unit
  tests — YAML has no meaningful "TDD" cycle. The workflow reuses the
  exact backend install recipe already documented in `README.md`'s
  "Backend" section, so it's expected to succeed on the first real run.
- Logging: `pytest`'s `caplog` fixture asserts specific log records are
  emitted on both the success and failure paths.
- Concurrency guardrail: `threading`-based tests that monkeypatch the
  module's semaphore down to size 1, occupy it from the test, and assert
  a second acquire attempt is correctly rejected (non-blocking) or
  correctly waits and then succeeds once released (blocking, with a short
  timeout to keep the test fast and deterministic).
- Docker: not exercised in CI (see Global Constraints in the
  implementation plan) — heavy ML dependencies make per-push image builds
  impractical at this scale. Verified manually via `docker compose build
  && docker compose up`, then hitting `/health` and loading the frontend.
