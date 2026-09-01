import { useState } from "react";
import { InputScreen } from "./components/InputScreen";
import { HistoryTab } from "./components/HistoryTab";
import { DifficultyTabs } from "./components/DifficultyTabs";
import type { TranscribeResponse } from "./api/types";
import "./App.css";

type View = "input" | "history";

function App() {
  const [result, setResult] = useState<TranscribeResponse | null>(null);
  const [view, setView] = useState<View>("input");

  return (
    <div className="app">
      <h1 className="app__title">Synthony</h1>
      {!result && (
        <div className="app__nav no-print" role="tablist">
          <button
            type="button"
            className="app__nav-tab"
            role="tab"
            aria-selected={view === "input"}
            onClick={() => setView("input")}
          >
            New
          </button>
          <button
            type="button"
            className="app__nav-tab"
            role="tab"
            aria-selected={view === "history"}
            onClick={() => setView("history")}
          >
            History
          </button>
        </div>
      )}
      {!result && view === "input" && <InputScreen onSuccess={setResult} />}
      {!result && view === "history" && <HistoryTab onSelect={setResult} />}
      {result && (
        <div className="app__result">
          <div className="app__result-header">
            <h2 className="app__result-title">{result.title}</h2>
            <button
              type="button"
              className="app__start-over no-print"
              onClick={() => {
                setResult(null);
                setView("input");
              }}
            >
              New transcription
            </button>
          </div>
          <DifficultyTabs result={result} />
        </div>
      )}
    </div>
  );
}

export default App;
