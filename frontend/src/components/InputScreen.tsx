import { UploadForm } from "./UploadForm";
import { QrScanButton } from "./QrScanButton";
import type { TranscribeResponse } from "../api/types";

interface InputScreenProps {
  onSuccess: (result: TranscribeResponse) => void;
}

export function InputScreen({ onSuccess }: InputScreenProps) {
  return (
    <div className="input-screen">
      <p className="input-screen__intro">
        Turn a solo piano recording into practice-ready sheet music at three
        difficulty levels — upload a file, paste a link, or scan a QR code.
      </p>
      <div className="input-screen__panel">
        <UploadForm onSuccess={onSuccess} />
        <div className="upload-form__divider">or</div>
        <QrScanButton onSuccess={onSuccess} />
      </div>
    </div>
  );
}
