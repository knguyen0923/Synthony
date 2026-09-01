import { useEffect, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { API_BASE_URL } from "../api/config";

interface ScoreViewerProps {
  musicXmlUrl: string;
  /** Used as the downloaded file's name; falls back to a generic name. */
  title?: string;
}

const ZOOM_STEP = 0.1;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2.5;

function resolveFullUrl(musicXmlUrl: string): string {
  return musicXmlUrl.startsWith("http") ? musicXmlUrl : `${API_BASE_URL}${musicXmlUrl}`;
}

function sanitizeFilename(name: string): string {
  return name.replace(/[/\\?%*:|"<>]/g, "-").trim() || "score";
}

export function ScoreViewer({ musicXmlUrl, title }: ScoreViewerProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const osmdRef = useRef<OpenSheetMusicDisplay | null>(null);
  const zoomRef = useRef(1.0);
  const [zoom, setZoomState] = useState(1.0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // A prior OSMD instance (from a previous render, a tab switch, or a
    // StrictMode double-invoke) may have already drawn into this container.
    // OSMD only clears elements it drew itself on re-render, so clear the
    // container before constructing a new instance to avoid scores stacking.
    el.innerHTML = "";
    const osmd = new OpenSheetMusicDisplay(el);
    osmdRef.current = osmd;
    let cancelled = false;

    (async () => {
      await osmd.load(resolveFullUrl(musicXmlUrl));
      if (!cancelled) {
        osmd.zoom = zoomRef.current;
        osmd.render();
      }
    })();

    return () => {
      cancelled = true;
      osmdRef.current = null;
      el.innerHTML = "";
    };
  }, [musicXmlUrl]);

  useEffect(() => {
    function handleFullscreenChange() {
      setIsFullscreen(document.fullscreenElement === wrapperRef.current);
    }
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  function applyZoom(next: number) {
    const clamped = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, next));
    zoomRef.current = clamped;
    setZoomState(clamped);
    const osmd = osmdRef.current;
    if (osmd) {
      osmd.zoom = clamped;
      osmd.render();
    }
  }

  function toggleFullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      wrapperRef.current?.requestFullscreen();
    }
  }

  async function downloadMusicXml() {
    setDownloadError(null);
    try {
      // A plain <a href download> is unreliable across a cross-origin
      // backend (localhost:8000 vs. the frontend's localhost:5173) — browsers
      // may just navigate instead of downloading. Fetching the file and
      // triggering the download from a same-origin blob: URL works reliably
      // regardless of the backend's origin or response headers.
      const response = await fetch(resolveFullUrl(musicXmlUrl));
      if (!response.ok) throw new Error("Download failed");
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = `${sanitizeFilename(title ?? "score")}.musicxml`;
      link.click();
      URL.revokeObjectURL(blobUrl);
    } catch {
      setDownloadError("Couldn't download the MusicXML file.");
    }
  }

  return (
    <div className="score-viewer" ref={wrapperRef}>
      <div className="score-viewer__toolbar no-print">
        <button type="button" onClick={() => applyZoom(zoom - ZOOM_STEP)} aria-label="Zoom out">
          −
        </button>
        <span className="score-viewer__zoom-level">{Math.round(zoom * 100)}%</span>
        <button type="button" onClick={() => applyZoom(zoom + ZOOM_STEP)} aria-label="Zoom in">
          +
        </button>
        <button type="button" onClick={toggleFullscreen}>
          {isFullscreen ? "Exit full screen" : "Full screen"}
        </button>
        <button type="button" onClick={downloadMusicXml}>
          Download MusicXML
        </button>
        <button type="button" onClick={() => window.print()}>
          Print / Save as PDF
        </button>
      </div>
      {downloadError && (
        <p className="upload-form__error no-print" role="alert">
          {downloadError}
        </p>
      )}
      <div className="score-viewer__sheet" ref={containerRef} />
    </div>
  );
}
