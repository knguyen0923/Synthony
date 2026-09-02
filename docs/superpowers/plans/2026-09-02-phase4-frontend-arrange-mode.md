# Frontend "Any Song" Input Mode (Spec 2, Phase 4 — frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the "Any song" input mode alongside "Solo piano recording" —
same three entry points (file/link/QR), routed to `POST /arrange` and
polling `GET /arrange/{job_id}` with a stage-aware progress indicator,
landing on the exact same result view Spec 1 already has.

**Architecture:** A new `api/arrange.ts` mirrors `api/transcribe.ts`'s
shape (submit → get a `TranscribeResponse`) but internally submits +
polls instead of a single blocking call, so from `InputScreen`'s
perspective both modes look identical: a function that takes a `File` or
URL string plus an optional progress callback, and resolves to a
`TranscribeResponse`. `UploadForm` and `QrScanButton` are made mode-agnostic
by accepting the submit functions as props instead of importing
`transcribeFile`/`transcribeLink` directly — this is the only structural
change to existing components, and it's additive (both existing call
sites keep working, just via props now). `DifficultyTabs`/`ScoreViewer`
need **zero changes**, since both pipelines resolve to the same
`TranscribeResponse` shape.

**Tech Stack:** React 18 + TypeScript, `axios` (existing dependency). No
new dependencies. This frontend has no test runner configured (no
Jest/Vitest) — verification is `npm run build` (tsc type-check + vite
build) and `npm run lint` after each task, matching how this codebase is
already verified elsewhere in `frontend/`. A human will do the actual
in-browser click-through afterward (starting the dev server and exercising
both modes) — this plan's steps stop at "compiles cleanly and lints
clean."

**Spec:** `docs/superpowers/specs/2026-09-01-any-song-arrangement-design.md`
(see "API Contract" for the exact `/arrange` request/response shapes,
"Frontend" section for the four required behaviors).

## Global Constraints

- `DifficultyTabs.tsx` and `ScoreViewer.tsx` are **not touched** — the
  spec explicitly says the result view needs no changes since both
  pipelines return the same shape.
- `App.tsx`'s `TranscribeResponse` state and `onSuccess` callback wiring
  are **not touched** — `InputScreen`'s `onSuccess` prop signature stays
  exactly as-is; only what happens *inside* `InputScreen` changes.
- No new dependencies (no polling library) — plain `setTimeout`-based
  polling, matching this codebase's preference for the simplest thing
  that works (see the backend's in-memory job store for the same
  philosophy).
- Progress-stage label text lives in one place (`api/arrange.ts`), not
  duplicated across components — `UploadForm`/`QrScanButton` just render
  whatever string they're given, with no knowledge of arrange-specific
  stage names.
- Verify with `cd frontend && npm run build && npm run lint` after every
  task — both must exit 0 before moving to the next task.

---

## File Structure

- Create: `frontend/src/api/arrange.ts`
- Modify: `frontend/src/api/transcribe.ts` (add an optional `onProgress`
  parameter to `transcribeFile`/`transcribeLink`, for interface
  consistency with the new arrange functions — existing callers are
  unaffected since it's optional)
- Modify: `frontend/src/components/UploadForm.tsx`
- Modify: `frontend/src/components/QrScanButton.tsx`
- Modify: `frontend/src/components/InputScreen.tsx`

## Task 1: `api/arrange.ts` — submit-and-poll matching `TranscribeResponse`'s shape

**Files:**
- Create: `frontend/src/api/arrange.ts`
- Modify: `frontend/src/api/transcribe.ts`

**Interfaces:**
- Consumes: `classifyLink` (existing, from `api/transcribe.ts`, already
  exported), `API_BASE_URL` (existing, from `api/config.ts`),
  `TranscribeResponse` (existing, from `api/types.ts`).
- Produces: `arrangeFile(file: File, onProgress?: (label: string) => void) -> Promise<TranscribeResponse>`
- Produces: `arrangeLink(url: string, onProgress?: (label: string) => void) -> Promise<TranscribeResponse>`
- Modifies: `transcribeFile`/`transcribeLink` in `api/transcribe.ts` gain
  an optional second `onProgress?: (label: string) => void` parameter,
  called once with `"Transcribing…"` right before the request — this
  keeps the exact same loading copy Solo Piano mode has today once
  `UploadForm` is made generic in Task 2.

- [ ] **Step 1: Add the optional progress parameter to `transcribe.ts`**

In `frontend/src/api/transcribe.ts`, change both exported functions:

```typescript
export async function transcribeFile(file: File, onProgress?: (label: string) => void): Promise<TranscribeResponse> {
  onProgress?.("Transcribing…");
  const form = new FormData();
  form.append("audio_file", file);
  const response = await axios.post<TranscribeResponse>(
    `${API_BASE_URL}/transcribe`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return response.data;
}
```

```typescript
export async function transcribeLink(url: string, onProgress?: (label: string) => void): Promise<TranscribeResponse> {
  const kind = classifyLink(url);
  if (kind === "invalid") {
    throw new Error("That doesn't look like a YouTube or Spotify link.");
  }

  onProgress?.("Transcribing…");
  const form = new FormData();
  form.append(kind === "spotify" ? "spotify_url" : "youtube_url", url);
  const response = await axios.post<TranscribeResponse>(
    `${API_BASE_URL}/transcribe`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return response.data;
}
```

(Only the function signatures and the one added `onProgress?.(...)` line
per function change — everything else in the file stays the same.)

- [ ] **Step 2: Write `api/arrange.ts`**

```typescript
// frontend/src/api/arrange.ts
import axios from "axios";
import type { TranscribeResponse } from "./types";
import { API_BASE_URL } from "./config";
import { classifyLink } from "./transcribe";

type ArrangeStage = "separating" | "extracting_melody" | "detecting_chords" | "arranging";

const STAGE_LABELS: Record<ArrangeStage, string> = {
  separating: "Separating vocals and instruments…",
  extracting_melody: "Extracting the melody…",
  detecting_chords: "Detecting chords…",
  arranging: "Arranging the accompaniment…",
};

const POLL_INTERVAL_MS = 1500;

interface ArrangeSubmitResponse {
  job_id: string;
  status: string;
}

type ArrangeStatusResponse =
  | { status: ArrangeStage }
  | { status: "failed"; detail: string }
  | TranscribeResponse;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollArrangeJob(
  jobId: string,
  onProgress?: (label: string) => void
): Promise<TranscribeResponse> {
  for (;;) {
    const response = await axios.get<ArrangeStatusResponse>(`${API_BASE_URL}/arrange/${jobId}`);
    const payload = response.data;

    if ("song_id" in payload) {
      return payload;
    }
    if (payload.status === "failed") {
      throw new Error(payload.detail);
    }
    onProgress?.(STAGE_LABELS[payload.status] ?? payload.status);
    await sleep(POLL_INTERVAL_MS);
  }
}

async function submitArrangeJob(
  form: FormData,
  onProgress?: (label: string) => void
): Promise<TranscribeResponse> {
  onProgress?.("Submitting…");
  const response = await axios.post<ArrangeSubmitResponse>(`${API_BASE_URL}/arrange`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return pollArrangeJob(response.data.job_id, onProgress);
}

export async function arrangeFile(file: File, onProgress?: (label: string) => void): Promise<TranscribeResponse> {
  const form = new FormData();
  form.append("audio_file", file);
  return submitArrangeJob(form, onProgress);
}

export async function arrangeLink(url: string, onProgress?: (label: string) => void): Promise<TranscribeResponse> {
  const kind = classifyLink(url);
  if (kind === "invalid") {
    throw new Error("That doesn't look like a YouTube or Spotify link.");
  }

  const form = new FormData();
  form.append(kind === "spotify" ? "spotify_url" : "youtube_url", url);
  return submitArrangeJob(form, onProgress);
}
```

- [ ] **Step 3: Verify it compiles and lints clean**

Run: `cd frontend && npm run build`
Expected: exits 0, no TypeScript errors (note: nothing imports
`arrangeFile`/`arrangeLink` yet, so an unused-export lint warning, if any,
is expected and resolves once Task 3 wires them in — don't treat that as
a failure at this step).

Run: `cd frontend && npm run lint`
Expected: exits 0

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/arrange.ts frontend/src/api/transcribe.ts
git commit -m "feat: add arrange API client (submit + poll /arrange job)"
```

## Task 2: Make `UploadForm` and `QrScanButton` mode-agnostic

**Files:**
- Modify: `frontend/src/components/UploadForm.tsx`
- Modify: `frontend/src/components/QrScanButton.tsx`

**Interfaces:**
- Modifies: `UploadFormProps` gains `submitFile: (file: File, onProgress: (label: string) => void) => Promise<TranscribeResponse>`
  and `submitLink: (url: string, onProgress: (label: string) => void) => Promise<TranscribeResponse>`,
  replacing the hardcoded `transcribeFile`/`transcribeLink` imports.
  (`transcribeFile`/`transcribeLink`'s `onProgress` parameter is
  optional, so passing them directly as these required-`onProgress` props
  type-checks fine — TypeScript allows a function with fewer parameters
  to satisfy a type expecting more.)
- Modifies: `QrScanButtonProps` gains `submitLink` with the same shape,
  replacing the hardcoded `transcribeLink` import.
- Both components' loading state now shows whatever label string they're
  given (starting at `"Working…"` before the first `onProgress` call, if
  any) instead of a hardcoded `"Transcribing…"`.

- [ ] **Step 1: Rewrite `UploadForm.tsx`**

```typescript
// frontend/src/components/UploadForm.tsx
import { useState } from "react";
import type { TranscribeResponse } from "../api/types";

interface UploadFormProps {
  onSuccess: (result: TranscribeResponse) => void;
  submitFile: (file: File, onProgress: (label: string) => void) => Promise<TranscribeResponse>;
  submitLink: (url: string, onProgress: (label: string) => void) => Promise<TranscribeResponse>;
}

function extractErrorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response
    ?.data?.detail;
  if (detail) return detail;
  if (err instanceof Error) return err.message;
  return "Something went wrong processing that audio.";
}

export function UploadForm({ onSuccess, submitFile, submitLink }: UploadFormProps) {
  const [link, setLink] = useState("");
  const [loading, setLoading] = useState(false);
  const [statusLabel, setStatusLabel] = useState("Working…");
  const [error, setError] = useState<string | null>(null);

  async function run(call: (onProgress: (label: string) => void) => Promise<TranscribeResponse>) {
    setLoading(true);
    setStatusLabel("Working…");
    setError(null);
    try {
      const result = await call(setStatusLabel);
      onSuccess(result);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    await run((onProgress) => submitFile(file, onProgress));
  }

  async function handleLinkSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!link.trim()) return;
    await run((onProgress) => submitLink(link.trim(), onProgress));
  }

  return (
    <div className="upload-form">
      <div className="upload-form__section">
        <label className="upload-form__label" htmlFor="audio-file-input">
          Upload a file
        </label>
        <input
          id="audio-file-input"
          type="file"
          accept=".wav,.mp3"
          onChange={handleFileChange}
          disabled={loading}
        />
      </div>

      <div className="upload-form__divider">or</div>

      <div className="upload-form__section">
        <label className="upload-form__label" htmlFor="link-input">
          Paste a link
        </label>
        <form className="upload-form__link-form" onSubmit={handleLinkSubmit}>
          <input
            id="link-input"
            type="text"
            placeholder="YouTube or Spotify link"
            value={link}
            onChange={(e) => setLink(e.target.value)}
            disabled={loading}
          />
          <button type="submit" disabled={loading}>
            Go
          </button>
        </form>
      </div>

      {loading && <p className="upload-form__status">{statusLabel}</p>}
      {error && (
        <p className="upload-form__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Rewrite `QrScanButton.tsx`**

```typescript
// frontend/src/components/QrScanButton.tsx
import { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import type { TranscribeResponse } from "../api/types";

interface QrScanButtonProps {
  onSuccess: (result: TranscribeResponse) => void;
  submitLink: (url: string, onProgress: (label: string) => void) => Promise<TranscribeResponse>;
}

const SCANNER_ELEMENT_ID = "qr-scanner-region";

function extractErrorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response
    ?.data?.detail;
  if (detail) return detail;
  if (err instanceof Error) return err.message;
  return "Couldn't process the scanned link.";
}

export function QrScanButton({ onSuccess, submitLink }: QrScanButtonProps) {
  const [scanning, setScanning] = useState(false);
  const [statusLabel, setStatusLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scannerRef = useRef<Html5Qrcode | null>(null);

  useEffect(() => {
    if (!scanning) return;

    const scanner = new Html5Qrcode(SCANNER_ELEMENT_ID);
    scannerRef.current = scanner;
    // html5-qrcode doesn't reliably release the camera if stop() is called
    // before start() has actually resolved (e.g. the camera-permission
    // prompt is still pending when this unmounts). Track whether start()
    // has resolved yet so cleanup only calls stop() once it's safe to.
    let cancelled = false;
    let started = false;

    scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: 250 },
        async (decodedText) => {
          await scanner.stop();
          setScanning(false);
          setStatusLabel("Working…");
          try {
            const result = await submitLink(decodedText, setStatusLabel);
            onSuccess(result);
          } catch (err) {
            setError(extractErrorMessage(err));
          } finally {
            setStatusLabel(null);
          }
        },
        () => {
          // per-frame scan failure — ignored, scanning continues
        }
      )
      .then(() => {
        if (cancelled) {
          // Unmounted while start() was pending — safe to stop now that it
          // has actually finished starting.
          scanner.stop().catch(() => {});
        } else {
          started = true;
        }
      })
      .catch(() => setError("Could not access the camera."));

    return () => {
      cancelled = true;
      if (started) {
        scanner.stop().catch(() => {});
      }
    };
  }, [scanning]);

  return (
    <div className="qr-scan-button">
      <label className="upload-form__label">Scan a QR code</label>
      <button onClick={() => setScanning(true)} disabled={scanning}>
        Scan QR code
      </button>
      {scanning && <div id={SCANNER_ELEMENT_ID} className="qr-scan-button__region" />}
      {statusLabel && <p className="upload-form__status">{statusLabel}</p>}
      {error && (
        <p className="upload-form__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify it compiles and lints clean**

`InputScreen.tsx` still passes `onSuccess` only at this point (Task 3
wires the new required props), so `npm run build` **will fail here** with
missing-prop errors on `<UploadForm ... />` / `<QrScanButton ... />` in
`InputScreen.tsx` — that's expected at this intermediate step, not a bug
in this task's own files. Confirm the errors are specifically about
`InputScreen.tsx` missing `submitFile`/`submitLink`, not about anything
inside `UploadForm.tsx` or `QrScanButton.tsx` themselves:

Run: `cd frontend && npx tsc --noEmit -p . 2>&1 | grep -v InputScreen.tsx || true`
Expected: no output (i.e. every reported error is in `InputScreen.tsx`)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/UploadForm.tsx frontend/src/components/QrScanButton.tsx
git commit -m "feat: make UploadForm and QrScanButton mode-agnostic via submit props"
```

## Task 3: Mode toggle in `InputScreen`

**Files:**
- Modify: `frontend/src/components/InputScreen.tsx`

**Interfaces:**
- Consumes: `transcribeFile`/`transcribeLink` (`api/transcribe.ts`),
  `arrangeFile`/`arrangeLink` (`api/arrange.ts`, Task 1), the now-generic
  `UploadForm`/`QrScanButton` (Task 2).
- `InputScreenProps` is unchanged (`onSuccess: (result: TranscribeResponse) => void`)
  — `App.tsx` needs no changes at all.

- [ ] **Step 1: Rewrite `InputScreen.tsx`**

```typescript
// frontend/src/components/InputScreen.tsx
import { useState } from "react";
import { UploadForm } from "./UploadForm";
import { QrScanButton } from "./QrScanButton";
import { transcribeFile, transcribeLink } from "../api/transcribe";
import { arrangeFile, arrangeLink } from "../api/arrange";
import type { TranscribeResponse } from "../api/types";

interface InputScreenProps {
  onSuccess: (result: TranscribeResponse) => void;
}

type Mode = "transcribe" | "arrange";

export function InputScreen({ onSuccess }: InputScreenProps) {
  const [mode, setMode] = useState<Mode>("transcribe");

  return (
    <div className="input-screen">
      <div className="app__nav" role="tablist">
        <button
          type="button"
          className="app__nav-tab"
          role="tab"
          aria-selected={mode === "transcribe"}
          onClick={() => setMode("transcribe")}
        >
          Solo piano recording
        </button>
        <button
          type="button"
          className="app__nav-tab"
          role="tab"
          aria-selected={mode === "arrange"}
          onClick={() => setMode("arrange")}
        >
          Any song
        </button>
      </div>

      <p className="input-screen__intro">
        {mode === "transcribe"
          ? "Turn a solo piano recording into practice-ready sheet music at three difficulty levels — upload a file, paste a link, or scan a QR code."
          : "Turn any song into an original piano arrangement — melody in the right hand, a new accompaniment in the left — upload a file, paste a link, or scan a QR code."}
      </p>

      <div className="input-screen__panel">
        {mode === "transcribe" ? (
          <>
            <UploadForm onSuccess={onSuccess} submitFile={transcribeFile} submitLink={transcribeLink} />
            <div className="upload-form__divider">or</div>
            <QrScanButton onSuccess={onSuccess} submitLink={transcribeLink} />
          </>
        ) : (
          <>
            <UploadForm onSuccess={onSuccess} submitFile={arrangeFile} submitLink={arrangeLink} />
            <div className="upload-form__divider">or</div>
            <QrScanButton onSuccess={onSuccess} submitLink={arrangeLink} />
          </>
        )}
      </div>
    </div>
  );
}
```

Note: this reuses the existing `app__nav`/`app__nav-tab` CSS classes
(already defined in `App.css` for the New/History top-level nav) for the
mode toggle's pill-tab look — no new CSS needed.

- [ ] **Step 2: Verify it compiles and lints clean**

Run: `cd frontend && npm run build`
Expected: exits 0, no TypeScript errors

Run: `cd frontend && npm run lint`
Expected: exits 0

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/InputScreen.tsx
git commit -m "feat: add Any Song input mode toggle to InputScreen"
```

## Out of Scope for This Plan

- Any change to `App.tsx`, `DifficultyTabs.tsx`, `ScoreViewer.tsx`,
  `HistoryTab.tsx` — all reuse the identical `TranscribeResponse` shape
  unchanged, per the spec's Frontend section.
- Automated frontend tests — this codebase has no test runner configured
  for the frontend at all (verified: no Jest/Vitest in `package.json`);
  introducing one is a larger, separate decision, not part of adding this
  feature.
- In-browser verification — a human (or an agent with browser tools)
  should start the dev server and click through both modes (file upload,
  link paste, and — if a camera is available — QR scan) after this plan
  is executed, before considering Phase 4's frontend done.
