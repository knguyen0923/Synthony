import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { UploadForm } from "./UploadForm";
import type { TranscribeResponse } from "../api/types";

const RESULT: TranscribeResponse = {
  song_id: "song-1",
  title: "Test Song",
  difficulties: {
    easy: { musicxml_url: "/easy.musicxml" },
    medium: { musicxml_url: "/medium.musicxml" },
    hard: { musicxml_url: "/hard.musicxml" },
  },
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("UploadForm", () => {
  it("calls submitLink (not submitFile) when the link form is submitted", async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    const submitFile = vi.fn();
    const submitLink = vi.fn().mockResolvedValue(RESULT);

    render(<UploadForm onSuccess={onSuccess} submitFile={submitFile} submitLink={submitLink} />);

    await user.type(screen.getByPlaceholderText("YouTube or Spotify link"), "https://youtu.be/abc");
    await user.click(screen.getByRole("button", { name: "Go" }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(RESULT));
    expect(submitLink).toHaveBeenCalledWith("https://youtu.be/abc", expect.any(Function));
    expect(submitFile).not.toHaveBeenCalled();
  });

  it("does not submit an empty/whitespace-only link", async () => {
    const user = userEvent.setup();
    const submitLink = vi.fn();

    render(
      <UploadForm
        onSuccess={vi.fn()}
        submitFile={vi.fn()}
        submitLink={submitLink}
      />
    );

    await user.type(screen.getByPlaceholderText("YouTube or Spotify link"), "   ");
    await user.click(screen.getByRole("button", { name: "Go" }));

    expect(submitLink).not.toHaveBeenCalled();
  });

  it("shows a loading state while the submission is pending, then clears it", async () => {
    const user = userEvent.setup();
    const { promise, resolve } = deferred<TranscribeResponse>();
    const submitLink = vi.fn().mockReturnValue(promise);

    render(<UploadForm onSuccess={vi.fn()} submitFile={vi.fn()} submitLink={submitLink} />);

    await user.type(screen.getByPlaceholderText("YouTube or Spotify link"), "https://youtu.be/abc");
    await user.click(screen.getByRole("button", { name: "Go" }));

    expect(await screen.findByText("Working…")).toBeInTheDocument();

    resolve(RESULT);
    await waitFor(() => expect(screen.queryByText("Working…")).not.toBeInTheDocument());
  });

  it("surfaces the extracted error message and clears loading state on failure", async () => {
    const user = userEvent.setup();
    const submitLink = vi.fn().mockRejectedValue({
      response: { data: { detail: "Audio capped at 10 minutes." } },
    });

    render(<UploadForm onSuccess={vi.fn()} submitFile={vi.fn()} submitLink={submitLink} />);

    await user.type(screen.getByPlaceholderText("YouTube or Spotify link"), "https://youtu.be/abc");
    await user.click(screen.getByRole("button", { name: "Go" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Audio capped at 10 minutes.");
    expect(screen.queryByText("Working…")).not.toBeInTheDocument();
  });

  it("calls submitFile (not submitLink) when a file is chosen", async () => {
    const user = userEvent.setup();
    const onSuccess = vi.fn();
    const submitFile = vi.fn().mockResolvedValue(RESULT);
    const submitLink = vi.fn();
    const file = new File(["fake audio bytes"], "song.mp3", { type: "audio/mpeg" });

    render(<UploadForm onSuccess={onSuccess} submitFile={submitFile} submitLink={submitLink} />);

    const input = screen.getByLabelText("Upload a file") as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith(RESULT));
    expect(submitFile).toHaveBeenCalledWith(file, expect.any(Function));
    expect(submitLink).not.toHaveBeenCalled();
  });

  it("ignores a second file-change while the first submission is still in flight", async () => {
    const user = userEvent.setup();
    const { promise, resolve } = deferred<TranscribeResponse>();
    const submitFile = vi.fn().mockReturnValue(promise);
    const file = new File(["fake audio bytes"], "song.mp3", { type: "audio/mpeg" });

    render(<UploadForm onSuccess={vi.fn()} submitFile={submitFile} submitLink={vi.fn()} />);

    const input = screen.getByLabelText("Upload a file") as HTMLInputElement;
    await user.upload(input, file);
    await user.upload(input, file);

    resolve(RESULT);
    await waitFor(() => expect(screen.queryByText("Working…")).not.toBeInTheDocument());
    expect(submitFile).toHaveBeenCalledTimes(1);
  });

  it("resets the file input value after handling so the same file can be re-selected", async () => {
    const user = userEvent.setup();
    const submitFile = vi.fn().mockRejectedValue(new Error("boom"));
    const file = new File(["fake audio bytes"], "song.mp3", { type: "audio/mpeg" });

    render(<UploadForm onSuccess={vi.fn()} submitFile={submitFile} submitLink={vi.fn()} />);

    const input = screen.getByLabelText("Upload a file") as HTMLInputElement;
    await user.upload(input, file);

    await waitFor(() => expect(input.value).toBe(""));
  });
});
