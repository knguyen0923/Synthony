import { useEffect, useRef } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

interface ScoreViewerProps {
  musicXmlUrl: string;
}

export function ScoreViewer({ musicXmlUrl }: ScoreViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // A prior OSMD instance (from a previous render, a tab switch, or a
    // StrictMode double-invoke) may have already drawn into this container.
    // OSMD only clears elements it drew itself on re-render, so clear the
    // container before constructing a new instance to avoid scores stacking.
    el.innerHTML = "";
    const osmd = new OpenSheetMusicDisplay(el);
    let cancelled = false;

    (async () => {
      const fullUrl = musicXmlUrl.startsWith("http")
        ? musicXmlUrl
        : `http://localhost:8000${musicXmlUrl}`;
      await osmd.load(fullUrl);
      if (!cancelled) {
        osmd.render();
      }
    })();

    return () => {
      cancelled = true;
      el.innerHTML = "";
    };
  }, [musicXmlUrl]);

  return <div ref={containerRef} />;
}
