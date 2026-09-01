import axios from "axios";
import type { TranscribeResponse } from "./types";

const API_BASE_URL = "http://localhost:8000";

export async function transcribeFile(file: File): Promise<TranscribeResponse> {
  const form = new FormData();
  form.append("audio_file", file);
  const response = await axios.post<TranscribeResponse>(
    `${API_BASE_URL}/transcribe`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return response.data;
}

export async function transcribeLink(url: string): Promise<TranscribeResponse> {
  const form = new FormData();
  if (url.includes("spotify.com")) {
    form.append("spotify_url", url);
  } else {
    form.append("youtube_url", url);
  }
  const response = await axios.post<TranscribeResponse>(
    `${API_BASE_URL}/transcribe`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return response.data;
}
