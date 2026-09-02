// frontend/src/api/arrange.ts
import axios from "axios";
import type { TranscribeResponse } from "./types";
import { API_BASE_URL } from "./config";
import { classifyLink } from "./transcribe";

type ArrangeStage = "separating" | "extracting_melody" | "detecting_key" | "arranging";

const STAGE_LABELS: Record<ArrangeStage, string> = {
  separating: "Separating vocals and instruments…",
  extracting_melody: "Extracting the melody…",
  detecting_key: "Detecting the key…",
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
