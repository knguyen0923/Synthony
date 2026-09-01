import { useState } from "react";
import { UploadForm } from "./components/UploadForm";
import { QrScanButton } from "./components/QrScanButton";
import { DifficultyTabs } from "./components/DifficultyTabs";
import type { TranscribeResponse } from "./api/types";

function App() {
  const [result, setResult] = useState<TranscribeResponse | null>(null);

  return (
    <div>
      <h1>Synthony</h1>
      {!result && (
        <>
          <UploadForm onSuccess={setResult} />
          <QrScanButton onSuccess={setResult} />
        </>
      )}
      {result && <DifficultyTabs result={result} />}
    </div>
  );
}

export default App;
