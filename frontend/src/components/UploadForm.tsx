// frontend/src/components/UploadForm.tsx
import { useEffect, useRef, useState } from "react";
import type { TranscribeResponse } from "../api/types";
import { extractErrorMessage } from "../api/errors";

interface UploadFormProps {
  onSuccess: (result: TranscribeResponse) => void;
  submitFile: (file: File, onProgress: (label: string) => void) => Promise<TranscribeResponse>;
  submitLink: (url: string, onProgress: (label: string) => void) => Promise<TranscribeResponse>;
}

export function UploadForm({ onSuccess, submitFile, submitLink }: UploadFormProps) {
  const [link, setLink] = useState("");
  const [loading, setLoading] = useState(false);
  const [statusLabel, setStatusLabel] = useState("Working…");
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  async function run(call: (onProgress: (label: string) => void) => Promise<TranscribeResponse>) {
    if (loading) return;
    setLoading(true);
    setStatusLabel("Working…");
    setError(null);
    try {
      const result = await call((label) => {
        if (mountedRef.current) setStatusLabel(label);
      });
      if (mountedRef.current) onSuccess(result);
    } catch (err) {
      if (mountedRef.current) {
        setError(extractErrorMessage(err, "Something went wrong processing that audio."));
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const input = event.target;
    const file = input.files?.[0];
    if (!file) return;
    await run((onProgress) => submitFile(file, onProgress));
    input.value = "";
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
