import axios from "axios";
import type { TranscribeResponse } from "./types";
import { API_BASE_URL } from "./config";

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

export type LinkKind = "youtube" | "spotify" | "invalid";

/** Classify a pasted link by hostname so ingestion routing (and client-side
 * validation) don't rely on a substring match that would silently forward
 * arbitrary text to yt-dlp. */
export function classifyLink(url: string): LinkKind {
  let hostname: string;
  try {
    hostname = new URL(url).hostname.toLowerCase();
  } catch {
    return "invalid";
  }

  if (hostname === "youtube.com" || hostname.endsWith(".youtube.com") || hostname === "youtu.be") {
    return "youtube";
  }
  if (hostname === "spotify.com" || hostname.endsWith(".spotify.com")) {
    return "spotify";
  }
  return "invalid";
}

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
