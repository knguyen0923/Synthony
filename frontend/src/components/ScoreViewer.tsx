import { useEffect, useRef } from "react";
import { OpenSheetMusicDisplay } from "opensheetmusicdisplay";

interface ScoreViewerProps {
  musicXmlUrl: string;
}

export function ScoreViewer({ musicXmlUrl }: ScoreViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const osmd = new OpenSheetMusicDisplay(containerRef.current);
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
    };
  }, [musicXmlUrl]);

  return <div ref={containerRef} />;
}
