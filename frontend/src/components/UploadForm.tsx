import { useState } from "react";
import { transcribeFile, transcribeLink } from "../api/transcribe";
import type { TranscribeResponse } from "../api/types";

interface UploadFormProps {
  onSuccess: (result: TranscribeResponse) => void;
}

function extractErrorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response
    ?.data?.detail;
  return detail ?? "Something went wrong transcribing that audio.";
}

export function UploadForm({ onSuccess }: UploadFormProps) {
  const [link, setLink] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runTranscription(call: () => Promise<TranscribeResponse>) {
    setLoading(true);
    setError(null);
    try {
      const result = await call();
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
    await runTranscription(() => transcribeFile(file));
  }

  async function handleLinkSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!link.trim()) return;
    await runTranscription(() => transcribeLink(link.trim()));
  }

  return (
    <div>
      <input type="file" accept=".wav,.mp3" onChange={handleFileChange} />
      <form onSubmit={handleLinkSubmit}>
        <input
          type="text"
          placeholder="Paste a YouTube or Spotify link"
          value={link}
          onChange={(e) => setLink(e.target.value)}
        />
        <button type="submit">Transcribe</button>
      </form>
      {loading && <p>Transcribing…</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
