export type Difficulty = "easy" | "medium" | "hard";

export interface DifficultyLink {
  musicxml_url: string;
}

export interface TranscribeResponse {
  song_id: string;
  title: string;
  difficulties: Record<Difficulty, DifficultyLink>;
}
