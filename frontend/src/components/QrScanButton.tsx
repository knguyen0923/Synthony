import { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { transcribeLink } from "../api/transcribe";
import type { TranscribeResponse } from "../api/types";

interface QrScanButtonProps {
  onSuccess: (result: TranscribeResponse) => void;
}

const SCANNER_ELEMENT_ID = "qr-scanner-region";

function extractErrorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response
    ?.data?.detail;
  return detail ?? "Couldn't transcribe the scanned link.";
}

export function QrScanButton({ onSuccess }: QrScanButtonProps) {
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scannerRef = useRef<Html5Qrcode | null>(null);

  useEffect(() => {
    if (!scanning) return;

    const scanner = new Html5Qrcode(SCANNER_ELEMENT_ID);
    scannerRef.current = scanner;

    scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: 250 },
        async (decodedText) => {
          await scanner.stop();
          setScanning(false);
          try {
            const result = await transcribeLink(decodedText);
            onSuccess(result);
          } catch (err) {
            setError(extractErrorMessage(err));
          }
        },
        () => {
          // per-frame scan failure — ignored, scanning continues
        }
      )
      .catch(() => setError("Could not access the camera."));

    return () => {
      scannerRef.current?.stop().catch(() => {});
    };
  }, [scanning]);

  return (
    <div>
      <button onClick={() => setScanning(true)}>Scan QR code</button>
      {scanning && <div id={SCANNER_ELEMENT_ID} />}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
