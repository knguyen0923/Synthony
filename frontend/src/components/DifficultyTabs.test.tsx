import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DifficultyTabs } from "./DifficultyTabs";
import type { TranscribeResponse } from "../api/types";

vi.mock("./ScoreViewer", () => ({
  ScoreViewer: ({ musicXmlUrl, title }: { musicXmlUrl: string; title?: string }) => (
    <div data-testid="score-viewer" data-url={musicXmlUrl} data-title={title} />
  ),
}));

const RESULT: TranscribeResponse = {
  song_id: "song-1",
  title: "Test Song",
  difficulties: {
    easy: { musicxml_url: "/easy.musicxml" },
    medium: { musicxml_url: "/medium.musicxml" },
    hard: { musicxml_url: "/hard.musicxml" },
  },
};

describe("DifficultyTabs", () => {
  it("defaults to the easy tier", () => {
    render(<DifficultyTabs result={RESULT} />);
    expect(screen.getByTestId("score-viewer")).toHaveAttribute("data-url", "/easy.musicxml");
    expect(screen.getByRole("tab", { name: "Easy" })).toHaveAttribute("aria-selected", "true");
  });

  it("switches ScoreViewer's url and title when a different tab is clicked", async () => {
    const user = userEvent.setup();
    render(<DifficultyTabs result={RESULT} />);

    await user.click(screen.getByRole("tab", { name: "Hard" }));

    const viewer = screen.getByTestId("score-viewer");
    expect(viewer).toHaveAttribute("data-url", "/hard.musicxml");
    expect(viewer).toHaveAttribute("data-title", "Test Song (hard)");
    expect(screen.getByRole("tab", { name: "Hard" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Easy" })).toHaveAttribute("aria-selected", "false");
  });
});
