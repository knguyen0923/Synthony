import { useEffect, useRef, useState } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";
import { jsPDF } from "jspdf";
import { svg2pdf } from "svg2pdf.js";
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
  const [actionError, setActionError] = useState<string | null>(null);
  const [isExportingPdf, setIsExportingPdf] = useState(false);

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

  useEffect(() => {
    // OSMD's on-screen layout ("Endless") is one continuous flow with no
    // internal page boundaries, so browser printing has to slice it wherever
    // the physical page ends — often mid-staff. Switching to a real paginated
    // layout only for the print action lets OSMD lay out proper page breaks
    // that respect whole systems; switch back afterward for the continuous
    // on-screen view. Covers both the Print button (window.print()) and the
    // browser's native print shortcut (Cmd/Ctrl+P), since both fire these
    // events.
    function handleBeforePrint() {
      const osmd = osmdRef.current;
      if (!osmd) return;
      osmd.setPageFormat("Letter_P");
      osmd.render();
    }
    function handleAfterPrint() {
      const osmd = osmdRef.current;
      if (!osmd) return;
      osmd.setPageFormat("Endless");
      osmd.render();
    }
    window.addEventListener("beforeprint", handleBeforePrint);
    window.addEventListener("afterprint", handleAfterPrint);
    return () => {
      window.removeEventListener("beforeprint", handleBeforePrint);
      window.removeEventListener("afterprint", handleAfterPrint);
    };
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
    setActionError(null);
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
      setActionError("Couldn't download the MusicXML file.");
    }
  }

  async function downloadPdf() {
    const osmd = osmdRef.current;
    const container = containerRef.current;
    if (!osmd || !container) return;

    setActionError(null);
    setIsExportingPdf(true);
    try {
      // Reuse the same paginated ("Letter_P") layout the print flow switches
      // to, so PDF pages break at the same whole-system boundaries instead of
      // wherever OSMD's continuous on-screen layout happens to run.
      osmd.setPageFormat("Letter_P");
      osmd.render();

      const pageDivs = Array.from(
        container.querySelectorAll<HTMLElement>('[id^="osmdCanvasPage"]')
      ).sort((a, b) => Number(a.id.slice("osmdCanvasPage".length)) - Number(b.id.slice("osmdCanvasPage".length)));
      const pageSvgs = pageDivs
        .map((div) => div.querySelector("svg"))
        .filter((svg): svg is SVGSVGElement => svg !== null);
      if (pageSvgs.length === 0) throw new Error("No rendered pages found");

      const width = pageSvgs[0].width.baseVal.value;
      const height = pageSvgs[0].height.baseVal.value;
      const pdf = new jsPDF({ unit: "px", format: [width, height] });

      for (let i = 0; i < pageSvgs.length; i++) {
        if (i > 0) pdf.addPage([width, height]);
        await svg2pdf(pageSvgs[i], pdf, { x: 0, y: 0, width, height });
      }
      pdf.save(`${sanitizeFilename(title ?? "score")}.pdf`);
    } catch {
      setActionError("Couldn't export the PDF.");
    } finally {
      osmd.setPageFormat("Endless");
      osmd.render();
      setIsExportingPdf(false);
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
        <button type="button" onClick={downloadPdf} disabled={isExportingPdf}>
          {isExportingPdf ? "Exporting PDF…" : "Download PDF"}
        </button>
        <button type="button" onClick={() => window.print()}>
          Print
        </button>
      </div>
      {actionError && (
        <p className="upload-form__error no-print" role="alert">
          {actionError}
        </p>
      )}
      <div className="score-viewer__sheet" ref={containerRef} />
    </div>
  );
}
