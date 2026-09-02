import { useEffect, useState } from "react";
import { listSongs, getSong, deleteSong } from "../api/songs";
import type { SongSummary } from "../api/songs";
import type { TranscribeResponse } from "../api/types";

interface HistoryTabProps {
  onSelect: (result: TranscribeResponse) => void;
}

const SOURCE_LABELS: Record<SongSummary["source_type"], string> = {
  youtube: "YouTube",
  spotify: "Spotify",
  upload: "Upload",
};

const PIPELINE_LABELS: Record<SongSummary["pipeline"], string> = {
  transcribe: "Solo piano",
  arrange: "Any song",
};

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function HistoryTab({ onSelect }: HistoryTabProps) {
  const [songs, setSongs] = useState<SongSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    listSongs()
      .then(setSongs)
      .catch(() => setError("Couldn't load history."));
  }, []);

  const filteredSongs = songs?.filter((song) =>
    song.title.toLowerCase().includes(query.trim().toLowerCase())
  );

  async function handleOpen(songId: string) {
    setError(null);
    setOpeningId(songId);
    try {
      const result = await getSong(songId);
      onSelect(result);
    } catch {
      setError("That song is no longer available.");
      setSongs((current) => current?.filter((s) => s.song_id !== songId) ?? current);
    } finally {
      setOpeningId(null);
    }
  }

  async function handleDelete(songId: string) {
    setError(null);
    try {
      await deleteSong(songId);
      setSongs((current) => current?.filter((s) => s.song_id !== songId) ?? current);
    } catch {
      setError("Couldn't delete that song.");
    } finally {
      setPendingDeleteId(null);
    }
  }

  return (
    <div className="history-tab">
      {error && <p className="history-tab__error">{error}</p>}
      {songs === null && !error && <p className="history-tab__status">Loading…</p>}
      {songs?.length === 0 && <p className="history-tab__status">No songs transcribed yet.</p>}
      {songs && songs.length > 0 && (
        <input
          type="search"
          className="history-tab__search"
          placeholder="Search songs by title…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search songs by title"
        />
      )}
      {filteredSongs?.length === 0 && songs && songs.length > 0 && (
        <p className="history-tab__status">No songs match your search.</p>
      )}
      {filteredSongs && filteredSongs.length > 0 && (
        <ul className="history-tab__list">
          {filteredSongs.map((song) => (
            <li key={song.song_id} className="history-tab__row">
              <button
                type="button"
                className="history-tab__open"
                onClick={() => handleOpen(song.song_id)}
                disabled={openingId === song.song_id}
              >
                <span className="history-tab__title">{song.title}</span>
                <span className="history-tab__meta">
                  <span className="history-tab__pipeline">{PIPELINE_LABELS[song.pipeline]}</span>
                  <span className="history-tab__source">{SOURCE_LABELS[song.source_type]}</span>
                  <span className="history-tab__date">{formatDate(song.created_at)}</span>
                </span>
              </button>
              {pendingDeleteId === song.song_id ? (
                <span className="history-tab__confirm">
                  <button type="button" onClick={() => handleDelete(song.song_id)}>
                    Confirm
                  </button>
                  <button type="button" onClick={() => setPendingDeleteId(null)}>
                    Cancel
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  className="history-tab__delete"
                  aria-label={`Delete ${song.title}`}
                  onClick={() => setPendingDeleteId(song.song_id)}
                >
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
