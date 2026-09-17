# Building Synthony — Lessons Learned

Split out from `TAKEAWAYS.md` (which was growing past this project's own
~400-line file-size guideline) to keep that file's overview/stack/status
sections skimmable while preserving the full retrospective here. See
`TAKEAWAYS.md` for what the project does, the tech stack, architecture,
by-the-numbers summary, and current status/roadmap.

## What I actually learned, by area

### This is a "does it sound right" product, not a "does it pass" product

Unit tests on 2-second synthetic sine-wave fixtures repeatedly missed
real bugs: a MusicXML export crash that only showed up on irregular
real chord timings, tempo-relative threshold bugs that only misfired at
certain real BPMs, a melody-extraction octave artifact, a voice-count
rounding overshoot. None of those had a synthetic test case that would
have caught them — they only surfaced from running the actual pipeline
against actual songs and inspecting (or listening to) the output. The
whole project ended up running on a standing rule: after any change to
the arrangement/transcription pipeline, re-run a fixed real-audio corpus
(one solo piano recording, three real pop songs) before considering the
change done, not just the pytest suite.

### Metrics can actively mislead if you don't chase the root cause

Adding the real beat-map tempo fix caused a large, alarming-looking note
count drop. It would have been easy to assume that meant lost data. It
didn't — a controlled, order-reversed same-process test traced it to the
beat map correctly consolidating near-duplicate detections that the old
fixed-tempo grid had artificially spread apart. The number moving is not
the same thing as the number being wrong; you have to trace *why* before
trusting either direction.

### A delegated implementation's own tests aren't enough

A hand-splitting algorithm, built by a dispatched agent with its own
fresh test suite, shipped with a real tuning bug (a consolidation penalty
cheap enough that it let one wrong bundled assignment persist across
several onsets). The agent's own new tests never caught it. It only
surfaced the moment the module was integrated against this repo's
*existing* test suite. Lesson kept for the rest of the project:
integrate any delegated module through the pre-existing tests before
trusting it, never just the delegate's own.

### Root-cause the symptom, don't just cap it

A "too many simultaneous notes piled up in one hand" bug was originally
fixed by capping the max voice count after the fact — a reasonable patch,
but not the real fix. The actual cause was that a piano transcription
model's note *offset* reflects acoustic/pedal decay, not when the key was
actually released, so a sustained pedal was pinning many notes' written
durations to the same late release instant. The real fix, done later in
the project once the prerequisite music21 upgrade landed, was to notate
the pedal event itself (`PedalMark` spanners) instead of letting decay
silently inflate every note's duration underneath it — using signal the
transcription model was producing all along and had simply been
discarded.

### A plausible root-cause hypothesis still needs direct verification

Mid-investigation into Big Rock's "plays too slow" complaint, once a
half-time tempo-detection misread was confirmed by ear, the natural next
hypothesis was that the beat tracker was being fed an ambiguous signal —
it ran on a bass+other "harmony" mix, and Demucs already separates a
`drums` stem (unused anywhere in the codebase) that should carry a far
clearer, less ambiguous beat signal. That reasoning was sound but wrong:
running the same detector directly on Big Rock's real isolated drums
stem still misread it at ~107 BPM, identical to the harmony-mix result.
The half-time ambiguity turned out to live in the backbeat pattern's own
accent structure (a driving rock backbeat's strongest hits *are* at the
half-time rate), not in cross-instrument interference — isolating the
drums doesn't remove an ambiguity that isn't about instrument bleed in
the first place. The stem-routing change shipped anyway (harmless, fully
tested), but the actual fix still needs the originally-designed
onset-midpoint correction heuristic. Caught only because the "confirm
against real audio" habit extended to the fix itself, not just the bug.

**Follow-up**: the originally-designed onset-midpoint correction
heuristic was built next and *did* fix it — confirmed the same way,
against the same real cached audio: corrected `bpm_at()` moved from
~109-111 BPM to ~203-213 BPM (matching the user's by-ear confirmation),
and, more tellingly, the actual notated-duration histogram of a
regenerated Hard tier shifted from ~75-77% "16th note" (the original
readability complaint) to mostly quarter/eighth notes. That second check
mattered: it's a reminder that a beat map doesn't just feed a tempo
label, it drives real rhythm quantization throughout the pipeline
(`BeatMap.to_quarter_length()`), so verifying "the BPM number looks
right" isn't the same as verifying "the notated rhythm looks right" —
both needed checking, and only one is obvious to check for.

### A measured accuracy number beats "seems about as good as before"

The quality harness (`backend/scripts/quality_harness/`) diffs objective
metrics run-over-run — note count, voice count, pitch range — but it
never checked correctness against a known-right answer, only "did this
change move the numbers." A portfolio review flagged the gap: pull a
handful of MAESTRO clips (piano recordings paired with ground-truth
MIDI — the same corpus `piano_transcription_inference` was trained on),
run them through Spec 1's transcription function directly, and score
onset+pitch precision/recall/F1 against ground truth with `mir_eval`
(the standard MIR research library, not a hand-rolled matcher). The
harder part turned out to be getting the 5 test-split clips onto disk at
all: MAESTRO's audio only ships inside one ~108GB zip, and neither GCS
nor Hugging Face serves its individual extracted members as separate
URLs (confirmed directly — per-file URLs 404). `remotezip` reads the
zip's central directory and fetches only the requested member's bytes
via HTTP range requests, verified live before it went in a plan: an
~85MB member in ~5 seconds, not the time to pull 108GB. The real result,
run against 5 held-out test-split clips spanning 5 composers: aggregate
precision 0.977, recall 0.935, F1 0.956 over 7,707 ground-truth notes —
close to, but measurably below, the checkpoint's own reported training
F1 of 0.9677 (the number embedded in its filename), with the model
consistently dropping more true notes than it hallucinates (recall
trails precision on every clip, most on the densest/most virtuosic one).
That gap between "the model's own reported number" and "what it actually
does on held-out audio run through this exact pipeline" is precisely
what a diff-only harness can never surface.

### Construction-order isn't the same thing as perceived difficulty

The difficulty engine (`app/difficulty/easy.py`/`medium.py`/`hard.py`) is
pure rule-based `Part`-level transforms — quantize note density, cap
chord voicing at 3 tones, narrow register — with Hard as a pure
passthrough. By construction, Easy always has the fewest notes and the
narrowest range, Medium more of both, Hard the original in full: a
guaranteed complexity ordering. Nobody had checked whether that ordering
actually matches perceived sight-reading difficulty. Reusing the 5
MAESTRO clips from the ground-truth eval above (no new corpus needed —
just added as `transcribe` sources to the same `run_baseline.py`), a
self-rated 1-10 sight-readability score across all 15 tier outputs found
it mostly doesn't: Easy and Medium tied in 3 of 5 pieces, and Hard scored
*lower* than Medium in 3 of 5 — a real ordering violation, not just a
tie, despite Hard having strictly more notes by construction. The
free-text notes explain why: the rules simplify rhythm grid and left-hand
note *count*, but never touch melodic complexity, accidental density, or
leaps ("every note is a flat or sharp," "every note is a 16th or 32nd
note") — the things that actually drive sight-reading difficulty. Medium's
3-tone chord-voicing cap may even produce *less* intuitive harmonic
shapes than either Easy's single root note or Hard's original full chord,
which would explain Medium occasionally rating harder than Hard, not
easier. A small, self-rated n=5 sample is too thin to redesign the
difficulty engine on alone, but it's a real, measured signal — the same
category of gap the accuracy eval above surfaced for transcription,
just for perceived difficulty instead of note correctness.

### A heuristic proxy found a real issue on the first real run

The quality harness's own docstring admits a human still has to listen
to judge real quality — every run, no exceptions. With no labeled
good/bad-arrangement corpus to train a classifier on, the honest move was
a heuristic scorer instead: hand balance, register overlap, note-duration
sanity, voice-count sanity, and note-density sanity, all computed from
stats `metrics.py` already produces. Only one threshold (hand balance)
had a real calibration point to aim at — Big Rock's old, since-fixed
RH1169/LH29 hand-split defect — the rest are documented, upfront, as
reasonable guesses rather than validated thresholds. Run for real against
the existing 5-source corpus (not a synthetic smoke test) before calling
it done: `transcribe_moonlight_sonata` cleared all three tiers, but
`arrange_instrumental_big_rock`'s Medium and Hard tiers flagged a real
register-overlap issue — 41.5%/79.1% of right-hand notes sitting below
middle C — that nobody had previously surfaced, on a track everyone
already assumed was fixed. Not root-caused yet, and the threshold that
caught it (30% register overlap) was itself an unvalidated guess — but a
guessed threshold that surfaces a real, previously-invisible issue on its
very first real run is a stronger result than the guess deserved credit
for, and a good argument for shipping a coarse heuristic proxy rather
than waiting for a labeled dataset that doesn't exist.

### Check whether the backlog item is still true before designing the fix

The next backlog item said frontend correctness was "verified manually
in a browser only" and named three components needing tests. Checking
first (`npm run test`) before brainstorming a design found that premise
was stale: `DifficultyTabs.test.tsx` and `UploadForm.test.tsx` already
existed and passed, 2 of the 3 named components already covered, CI
already running the whole suite. The real gap was narrower than the
backlog claimed — just `ScoreViewer.tsx`, which the existing
`DifficultyTabs.test.tsx` mocks out entirely (`vi.mock("./ScoreViewer",
...)`) and so had never actually been exercised itself. Designing a test
suite from the backlog's own description would have re-covered ground
that was already solid and missed naming the one component that mattered.
A five-minute "does this still hold" check before any design work is
cheap insurance against building for a stale problem statement.

### A synthetic test can silently validate the wrong thing

Extending time-signature detection past the fixed-4/4 assumption meant
adding a new detector on top of madmom's joint beat+downbeat tracker, then
testing it the project's established way: real fluidsynth-synthesized
audio with known ground truth, not mocks. The first attempt used the same
identical-velocity click-track style the existing beat-tracking tests
already used successfully — and it looked like it worked, correctly
reporting 4/4 for a 4/4 pattern. Checking the intermediate values before
trusting that result found the real story: both the 4/4 and a 3/4 test
clip measured well under `has_audible_signal`'s RMS gate (sparse click
tracks are mostly silence by construction), so the detector had silently
taken its inaudible-audio fallback path — 4/4 — for both clips. The "4/4
result" was the fallback default matching the expected answer by pure
coincidence; the 3/4 clip's fallback-to-4/4 immediately exposed the
problem once actually checked. Fixed by peak-normalizing the synthesized
audio before writing it. A test passing is not the same as a test having
exercised the code path it claims to test — worth checking what a new
kind of synthetic fixture actually measures before trusting a green
result from it, especially the first time a fixture crosses paths with
an existing gate (like an RMS floor) built for different audio.

### Deliberately not swapping something is as important a decision as swapping it

Spec 2's left hand stayed on Basic Pitch even after a piano-specific
model proved dramatically better for Spec 1's solo-piano case. MT3 was
evaluated as a replacement and rejected on evidence (unmaintained in
practice, far slower on CPU, and redundant work given Demucs had already
separated the instruments). Not every "better model exists" is worth
acting on — the right question is whether it's better *for this specific
subtask*, not better in general.

### Infrastructure has its own gotchas, independent of the ML

- madmom (an unmaintained-since-~2022 dependency needed for real beat
  tracking) doesn't import on Python 3.10+ from its last PyPI release at
  all — the fix existed only on its GitHub main branch, at a commit that
  had to be pinned and installed with build isolation off, which itself
  required numpy/scipy/Cython/mido to already be present first.
- A stale backend process from before a Python version migration can sit
  on the same dev port a fresh one expects, silently serving old
  behavior — worth a `ps -p <pid> -o command` check on anything already
  listening before trusting it's current.
- When the usual browser-automation path wasn't available for a
  rendering-verification pass, a scratch Playwright+Chromium setup
  substituted in — the verification a change needs shouldn't depend on
  exactly one tool being available.

### Balanced metrics can still be the wrong answer

A follow-up bug in the hand-splitting algorithm (it forced every "lone
note" onset to the right hand unconditionally — correct for solo piano,
wrong for multi-instrument input) got a real, independently-verified fix.
But real-audio verification on the fix surfaced a second problem no
metric had flagged: the fixed algorithm produced a well-balanced RH/LH
note count on a rock instrumental (1169/29 → 670/540) yet sounded
"incoherent/scattered" by ear. Sweeping the tuning parameter against the
real note stream confirmed balance and flicker were in direct
opposition — a value strong enough to suppress the flicker just
recreated the original bug. The actual fix was structural, not a tuning
number: transcribe the bass and "other" stems *separately* (bass → LH,
other → RH) instead of mixing them into one signal and re-splitting by
continuity, since continuity-based splitting assumes one performer's two
hands, not two different instruments interleaved in time. Lesson: when a
metric and your ear disagree, trust the ear and go looking for a
structural cause, not a better-tuned constant.

### A discovery sweep is worth doing even with no new feature to build

Once both pipelines were stable, a dedicated pass ran a backend
`/code-review`, a backend error-handling audit, and a frontend
`/code-review` — not chasing any specific bug, just looking. It found
real, previously-unnoticed gaps: Spotify ingestion was unconditionally
broken in the default unconfigured state (`SpotifyOauthError` isn't a
subclass of the exception type the existing handler caught, confirmed by
direct execution, not just reading the code); a non-audio/corrupt upload
surfaced as a raw 500 instead of a clean 422; several React components
had real lifecycle bugs (a failed camera permission left a scan button
permanently disabled, a file input never reset after a failed upload,
state updates could fire after unmount). None of these were regressions
from a specific change — they'd been latent since whenever that code was
first written. Worth scheduling this kind of sweep periodically, not just
reacting to bugs the user happens to notice.

### Working with an AI coding assistant deliberately

- **Spec first, code second.** Non-trivial pipeline changes got a
  written design doc (`docs/superpowers/specs/`) before implementation —
  scope and edge cases get decided on purpose, not discovered mid-build.
- **Verify by listening, not by trusting the harness.** Automated metrics
  guided *where* to look, but tuning decisions (a Basic Pitch
  `minimum_note_length` change, several pipeline-stage changes) were only
  actually confirmed once a human listened to the real audio — mixed or
  inconclusive metrics were treated as "needs an ear," not "good enough."
- **Draw a hard line between reversible and not.** Local edits, tests,
  and commits happened freely; nothing here ever touched a production or
  live environment — this project's own working rule going in was the
  same instruction any assistant operates under: read from anywhere,
  write only to non-production. That boundary is what made fast local
  iteration possible without a second thought about blast radius.

### Production hardening surfaced its own class of lessons

Once the pipelines were solid, a separate pass added CI, structured
logging, a concurrency guardrail, and Docker support — deliberately scoped
to what a personal/demo project needs, not public-service infrastructure
(no auth, no rate limiting beyond the concurrency cap, no distributed job
queue). Running this as a plan with independent task-level review, plus
one broad whole-branch review at the end, caught things a single pass
wouldn't have:

- **A review that reproduces a claim beats a review that reads it.** A
  fix for "Docker doesn't pick up Spotify credentials from `backend/.env`"
  added an `env_file` directive that looked correct on paper. The
  re-review didn't just read the diff — it ran `docker compose config`
  against a real test `.env` and found the fix was completely inert: a
  pre-existing `environment:` block in the same file silently overrides
  `env_file` for identical keys in Docker Compose's precedence rules. The
  bug wasn't in unfamiliar code; it was in a two-line YAML file, and it
  still needed empirical reproduction to catch.
- **Real infrastructure findings don't always get a same-session fix, and
  that's fine if it's said out loud.** Two genuine, evidence-backed gaps
  ended this pass documented-but-unfixed rather than patched: the backend
  Docker image doesn't build natively on Apple Silicon at all (a `demucs`
  transitive dependency, `sphn`, ships no `linux/aarch64` wheel — confirmed
  by testing both an arm64 build and an emulated amd64 build side by side),
  and the docker-compose fix above. Attempting a real fix for the former
  (a Rust toolchain so `sphn` builds from source) would have needed a slow,
  uncertain verification cycle for the least-critical task in the plan;
  the honest move was a clear comment explaining the gap and a workaround,
  not a confident-looking but unverified patch.
- **A plan can specify a broken test, and a good implementer will catch
  it, not just follow it.** One task's own written instructions told an
  implementer to monkeypatch a semaphore reference on the wrong module.
  Patching it there would have made the test pass without actually testing
  anything (the object being patched was never read at runtime). Catching
  this required the implementer to trace *where* a value is actually
  looked up at call time, not just where a plan says to patch it — the
  written plan is an argument, not a substitute for reading the code.
