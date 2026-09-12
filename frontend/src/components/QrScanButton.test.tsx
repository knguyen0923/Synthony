import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QrScanButton } from "./QrScanButton";
import type { TranscribeResponse } from "../api/types";

const mockStart = vi.fn();
const mockStop = vi.fn().mockResolvedValue(undefined);

vi.mock("html5-qrcode", () => ({
  Html5Qrcode: vi.fn().mockImplementation(() => ({
    start: mockStart,
    stop: mockStop,
  })),
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

beforeEach(() => {
  mockStart.mockReset();
  mockStop.mockReset().mockResolvedValue(undefined);
});

describe("QrScanButton", () => {
  it("resets scanning state when the camera fails to start", async () => {
    const user = userEvent.setup();
    mockStart.mockRejectedValue(new Error("permission denied"));

    render(<QrScanButton onSuccess={vi.fn()} submitLink={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Scan QR code" }));

    expect(await screen.findByText("Could not access the camera.")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Scan QR code" })).not.toBeDisabled()
    );
  });

  it("resets any prior error message when starting a new scan", async () => {
    const user = userEvent.setup();
    mockStart.mockRejectedValueOnce(new Error("permission denied"));
    mockStart.mockImplementationOnce(() => new Promise(() => {})); // second attempt hangs deliberately

    render(<QrScanButton onSuccess={vi.fn()} submitLink={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Scan QR code" }));
    expect(await screen.findByText("Could not access the camera.")).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Scan QR code" })).not.toBeDisabled()
    );
    await user.click(screen.getByRole("button", { name: "Scan QR code" }));

    expect(screen.queryByText("Could not access the camera.")).not.toBeInTheDocument();
  });

  it("only processes a scan result once, even if the success callback fires again before stop() resolves", async () => {
    const submitLink = vi.fn().mockResolvedValue(RESULT);
    const onSuccess = vi.fn();
    let fireSuccess: (decodedText: string) => void = () => {};
    mockStart.mockImplementation((_config: unknown, _scanConfig: unknown, successCb: (text: string) => void) => {
      fireSuccess = successCb;
      return Promise.resolve();
    });
    // stop() resolves slowly, mirroring how a real second camera frame could
    // fire the success callback again before the first stop() settles.
    mockStop.mockImplementation(() => new Promise((resolve) => setTimeout(resolve, 20)));

    render(<QrScanButton onSuccess={onSuccess} submitLink={submitLink} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Scan QR code" }));
    await waitFor(() => expect(mockStart).toHaveBeenCalled());

    fireSuccess("decoded-text");
    fireSuccess("decoded-text"); // simulated duplicate frame

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(submitLink).toHaveBeenCalledTimes(1);
  });
});
