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
