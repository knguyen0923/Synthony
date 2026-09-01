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
  if (detail) return detail;
  if (err instanceof Error) return err.message;
  return "Couldn't transcribe the scanned link.";
}

export function QrScanButton({ onSuccess }: QrScanButtonProps) {
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scannerRef = useRef<Html5Qrcode | null>(null);

  useEffect(() => {
    if (!scanning) return;

    const scanner = new Html5Qrcode(SCANNER_ELEMENT_ID);
    scannerRef.current = scanner;
    // html5-qrcode doesn't reliably release the camera if stop() is called
    // before start() has actually resolved (e.g. the camera-permission
    // prompt is still pending when this unmounts). Track whether start()
    // has resolved yet so cleanup only calls stop() once it's safe to.
    let cancelled = false;
    let started = false;

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
      .then(() => {
        if (cancelled) {
          // Unmounted while start() was pending — safe to stop now that it
          // has actually finished starting.
          scanner.stop().catch(() => {});
        } else {
          started = true;
        }
      })
      .catch(() => setError("Could not access the camera."));

    return () => {
      cancelled = true;
      if (started) {
        scanner.stop().catch(() => {});
      }
    };
  }, [scanning]);

  return (
    <div className="qr-scan-button">
      <label className="upload-form__label">Scan a QR code</label>
      <button onClick={() => setScanning(true)} disabled={scanning}>
        Scan QR code
      </button>
      {scanning && <div id={SCANNER_ELEMENT_ID} className="qr-scan-button__region" />}
      {error && (
        <p className="upload-form__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
