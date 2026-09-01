import { useState } from "react";
import { ScoreViewer } from "./ScoreViewer";
import type { Difficulty, TranscribeResponse } from "../api/types";

interface DifficultyTabsProps {
  result: TranscribeResponse;
}

const TIERS: Difficulty[] = ["easy", "medium", "hard"];

export function DifficultyTabs({ result }: DifficultyTabsProps) {
  const [active, setActive] = useState<Difficulty>("easy");

  return (
    <div className="difficulty-tabs">
      <div className="difficulty-tabs__list no-print" role="tablist">
        {TIERS.map((tier) => (
          <button
            key={tier}
            className={`difficulty-tabs__tab difficulty-tabs__tab--${tier}`}
            role="tab"
            aria-selected={active === tier}
            onClick={() => setActive(tier)}
          >
            {tier[0].toUpperCase() + tier.slice(1)}
          </button>
        ))}
      </div>
      <ScoreViewer musicXmlUrl={result.difficulties[active].musicxml_url} title={`${result.title} (${active})`} />
    </div>
  );
}
