import { useState } from "react";
import { InputScreen } from "./components/InputScreen";
import { DifficultyTabs } from "./components/DifficultyTabs";
import type { TranscribeResponse } from "./api/types";
import "./App.css";

function App() {
  const [result, setResult] = useState<TranscribeResponse | null>(null);

  return (
    <div className="app">
      <h1 className="app__title">Synthony</h1>
      {!result && <InputScreen onSuccess={setResult} />}
      {result && (
        <div className="app__result">
          <div className="app__result-header">
            <h2 className="app__result-title">{result.title}</h2>
            <button
              type="button"
              className="app__start-over no-print"
              onClick={() => setResult(null)}
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
