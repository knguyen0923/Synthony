import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

// OSMD/jsPDF/svg2pdf are mocked at the module level (same technique
// DifficultyTabs.test.tsx already uses to mock ./ScoreViewer itself) --
// this tests ScoreViewer's own logic (zoom clamping, error handling,
// event wiring), not OSMD's real rendering or svg2pdf's real conversion.
const mockOsmd = vi.hoisted(() => ({
  load: vi.fn(),
  render: vi.fn(),
  setPageFormat: vi.fn(),
  zoom: 1,
}));
const MockOpenSheetMusicDisplay = vi.hoisted(() => vi.fn(() => mockOsmd));

vi.mock("opensheetmusicdisplay", () => ({
  OpenSheetMusicDisplay: MockOpenSheetMusicDisplay,
}));
vi.mock("jspdf", () => ({ jsPDF: vi.fn() }));
vi.mock("svg2pdf.js", () => ({ svg2pdf: vi.fn() }));

import { ScoreViewer } from "./ScoreViewer";

beforeEach(() => {
  vi.clearAllMocks();
  mockOsmd.load.mockResolvedValue(undefined);
  mockOsmd.zoom = 1;
});

describe("ScoreViewer", () => {
  it("loads the resolved full URL and renders at the default zoom", async () => {
    render(<ScoreViewer musicXmlUrl="/easy.musicxml" title="Test Song" />);

    await waitFor(() => expect(mockOsmd.load).toHaveBeenCalledWith("http://localhost:8000/easy.musicxml"));
    expect(mockOsmd.render).toHaveBeenCalled();
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("passes an already-absolute URL through unchanged", async () => {
    render(<ScoreViewer musicXmlUrl="https://example.com/song.musicxml" />);
    await waitFor(() => expect(mockOsmd.load).toHaveBeenCalledWith("https://example.com/song.musicxml"));
  });

  it("shows an error message when the score fails to load", async () => {
    mockOsmd.load.mockRejectedValue(new Error("network error"));
    render(<ScoreViewer musicXmlUrl="/broken.musicxml" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't load this score/i);
  });

  it("zoom buttons increment/decrement and clamp at 50%-250%, re-rendering each time", async () => {
    const user = userEvent.setup();
    render(<ScoreViewer musicXmlUrl="/easy.musicxml" />);
    await waitFor(() => expect(mockOsmd.load).toHaveBeenCalled());
    mockOsmd.render.mockClear();

    for (let i = 0; i < 20; i++) {
      await user.click(screen.getByRole("button", { name: "Zoom in" }));
    }
    expect(screen.getByText("250%")).toBeInTheDocument();
    expect(mockOsmd.zoom).toBe(2.5);

    for (let i = 0; i < 30; i++) {
      await user.click(screen.getByRole("button", { name: "Zoom out" }));
    }
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(mockOsmd.zoom).toBe(0.5);
    expect(mockOsmd.render).toHaveBeenCalled();
  });

  it("toggles fullscreen label when fullscreenchange fires", async () => {
    const user = userEvent.setup();
    const requestFullscreen = vi.fn().mockResolvedValue(undefined);
    Element.prototype.requestFullscreen = requestFullscreen;
    document.exitFullscreen = vi.fn().mockResolvedValue(undefined);

    render(<ScoreViewer musicXmlUrl="/easy.musicxml" />);
    await waitFor(() => expect(mockOsmd.load).toHaveBeenCalled());

    const button = screen.getByRole("button", { name: "Full screen" });
    await user.click(button);
    expect(requestFullscreen).toHaveBeenCalled();

    // Simulate the browser entering fullscreen on the wrapper element.
    Object.defineProperty(document, "fullscreenElement", {
      value: button.closest(".score-viewer"),
      configurable: true,
    });
    act(() => {
      document.dispatchEvent(new Event("fullscreenchange"));
    });

    expect(await screen.findByRole("button", { name: "Exit full screen" })).toBeInTheDocument();

    Object.defineProperty(document, "fullscreenElement", { value: null, configurable: true });
  });

  it("downloads the MusicXML file via a blob URL", async () => {
    const user = userEvent.setup();
    const blob = new Blob(["<xml/>"], { type: "application/xml" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, blob: () => Promise.resolve(blob) }));
    const createObjectURL = vi.fn().mockReturnValue("blob:fake-url");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    // jsdom attempts real navigation on <a>.click() even for blob: URLs it
    // can't resolve; not implemented in jsdom and not what this test cares
    // about (only that a blob download was triggered), so stub it out.
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<ScoreViewer musicXmlUrl="/easy.musicxml" title="My Song" />);
    await waitFor(() => expect(mockOsmd.load).toHaveBeenCalled());

    await user.click(screen.getByRole("button", { name: "Download MusicXML" }));

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledWith(blob));
    expect(anchorClick).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake-url");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    vi.unstubAllGlobals();
    anchorClick.mockRestore();
  });

  it("shows an error and resets loading state when PDF export finds no rendered pages", async () => {
    const user = userEvent.setup();
    render(<ScoreViewer musicXmlUrl="/easy.musicxml" />);
    await waitFor(() => expect(mockOsmd.load).toHaveBeenCalled());

    const pdfButton = screen.getByRole("button", { name: "Download PDF" });
    await user.click(pdfButton);

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't export the pdf/i);
    expect(screen.getByRole("button", { name: "Download PDF" })).not.toBeDisabled();
    expect(mockOsmd.setPageFormat).toHaveBeenCalledWith("Letter_P");
    expect(mockOsmd.setPageFormat).toHaveBeenCalledWith("Endless");
  });

  it("switches to a paginated layout for print and back afterward", async () => {
    render(<ScoreViewer musicXmlUrl="/easy.musicxml" />);
    await waitFor(() => expect(mockOsmd.load).toHaveBeenCalled());
    mockOsmd.render.mockClear();
    mockOsmd.setPageFormat.mockClear();

    window.dispatchEvent(new Event("beforeprint"));
    expect(mockOsmd.setPageFormat).toHaveBeenCalledWith("Letter_P");
    expect(mockOsmd.render).toHaveBeenCalledTimes(1);

    window.dispatchEvent(new Event("afterprint"));
    expect(mockOsmd.setPageFormat).toHaveBeenCalledWith("Endless");
    expect(mockOsmd.render).toHaveBeenCalledTimes(2);
  });
});
