// frontend/src/components/QrScanButton.tsx
import { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import type { TranscribeResponse } from "../api/types";
import { extractErrorMessage } from "../api/errors";

interface QrScanButtonProps {
  onSuccess: (result: TranscribeResponse) => void;
  submitLink: (url: string, onProgress: (label: string) => void) => Promise<TranscribeResponse>;
}

const SCANNER_ELEMENT_ID = "qr-scanner-region";

export function QrScanButton({ onSuccess, submitLink }: QrScanButtonProps) {
  const [scanning, setScanning] = useState(false);
  const [statusLabel, setStatusLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scannerRef = useRef<Html5Qrcode | null>(null);
  // Tracks whether the component itself is still mounted, independent of the
  // scanning-effect's own cleanup (which also runs when a successful scan
  // flips `scanning` back to false). State updates after a real scan success
  // must still land even though that effect cleanup fires.
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

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
    let handled = false;

    scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: 250 },
        async (decodedText) => {
          if (handled) return;
          handled = true;
          await scanner.stop();
          setScanning(false);
          setStatusLabel("Working…");
          try {
            const result = await submitLink(decodedText, (label) => {
              if (isMountedRef.current) setStatusLabel(label);
            });
            if (isMountedRef.current) onSuccess(result);
          } catch (err) {
            if (isMountedRef.current) {
              setError(extractErrorMessage(err, "Couldn't process the scanned link."));
            }
          } finally {
            if (isMountedRef.current) setStatusLabel(null);
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
      .catch(() => {
        setError("Could not access the camera.");
        setScanning(false);
      });

    return () => {
      cancelled = true;
      if (started) {
        scanner.stop().catch(() => {});
      }
    };
    // onSuccess/submitLink are recreated every parent render; depending on
    // them would restart the camera mid-scan whenever the parent re-renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanning]);

  return (
    <div className="qr-scan-button">
      <label className="upload-form__label">Scan a QR code</label>
      <button
        onClick={() => {
          setError(null);
          setScanning(true);
        }}
        disabled={scanning}
      >
        Scan QR code
      </button>
      {scanning && <div id={SCANNER_ELEMENT_ID} className="qr-scan-button__region" />}
      {statusLabel && <p className="upload-form__status">{statusLabel}</p>}
      {error && (
        <p className="upload-form__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
