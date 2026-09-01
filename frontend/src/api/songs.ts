import axios from "axios";
import type { TranscribeResponse } from "./types";
import { API_BASE_URL } from "./config";

export interface SongSummary {
  song_id: string;
  title: string;
  source_type: "upload" | "youtube" | "spotify";
  source_url: string | null;
  created_at: string;
}

export async function listSongs(): Promise<SongSummary[]> {
  const response = await axios.get<SongSummary[]>(`${API_BASE_URL}/songs`);
  return response.data;
}

export async function getSong(songId: string): Promise<TranscribeResponse> {
  const response = await axios.get<TranscribeResponse>(`${API_BASE_URL}/songs/${songId}`);
  return response.data;
}

export async function deleteSong(songId: string): Promise<void> {
  await axios.delete(`${API_BASE_URL}/songs/${songId}`);
}
