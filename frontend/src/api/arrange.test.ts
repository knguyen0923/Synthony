import axios from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { arrangeFile } from "./arrange";
import type { TranscribeResponse } from "./types";

vi.mock("axios");

const mockedAxios = vi.mocked(axios, true);

const RESULT: TranscribeResponse = {
  song_id: "song-1",
  title: "Test Song",
  difficulties: {
    easy: { musicxml_url: "/easy.musicxml" },
    medium: { musicxml_url: "/medium.musicxml" },
    hard: { musicxml_url: "/hard.musicxml" },
  },
};

const file = new File(["fake audio bytes"], "song.mp3", { type: "audio/mpeg" });

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("arrangeFile (submitArrangeJob + pollArrangeJob)", () => {
  it("submits, polls through intermediate stages, and resolves with the final result", async () => {
    mockedAxios.post.mockResolvedValueOnce({ data: { job_id: "job-1", status: "queued" } });
    mockedAxios.get
      .mockResolvedValueOnce({ data: { status: "separating" } })
      .mockResolvedValueOnce({ data: { status: "extracting_melody" } })
      .mockResolvedValueOnce({ data: RESULT });

    const onProgress = vi.fn();
    const promise = arrangeFile(file, onProgress);

    // Let the initial submit + first two polls run, advancing the fake
    // POLL_INTERVAL_MS timer between each.
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(1500);
    await vi.advanceTimersByTimeAsync(1500);

    const result = await promise;

    expect(result).toEqual(RESULT);
    expect(mockedAxios.get).toHaveBeenCalledTimes(3);
    expect(onProgress).toHaveBeenCalledWith("Submitting…");
    expect(onProgress).toHaveBeenCalledWith("Separating vocals and instruments…");
    expect(onProgress).toHaveBeenCalledWith("Extracting the melody…");
  });

  it("throws with the backend's detail message when the job fails", async () => {
    mockedAxios.post.mockResolvedValueOnce({ data: { job_id: "job-2", status: "queued" } });
    mockedAxios.get.mockResolvedValueOnce({
      data: { status: "failed", detail: "Stem separation failed." },
    });

    const promise = arrangeFile(file);
    const assertion = expect(promise).rejects.toThrow("Stem separation failed.");
    await vi.advanceTimersByTimeAsync(0);

    await assertion;
  });

  it("falls back to the raw stage name if a stage has no known label", async () => {
    mockedAxios.post.mockResolvedValueOnce({ data: { job_id: "job-3", status: "queued" } });
    mockedAxios.get
      .mockResolvedValueOnce({ data: { status: "some_future_stage" } })
      .mockResolvedValueOnce({ data: RESULT });

    const onProgress = vi.fn();
    const promise = arrangeFile(file, onProgress);
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(1500);

    await promise;

    expect(onProgress).toHaveBeenCalledWith("some_future_stage");
  });
});
