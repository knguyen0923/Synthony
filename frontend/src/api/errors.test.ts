import { describe, expect, it } from "vitest";
import { extractErrorMessage } from "./errors";

describe("extractErrorMessage", () => {
  it("prefers the backend's response.data.detail when present", () => {
    const err = { response: { data: { detail: "Audio capped at 10 minutes." } } };
    expect(extractErrorMessage(err, "fallback")).toBe("Audio capped at 10 minutes.");
  });

  it("falls back to Error.message when there's no response detail", () => {
    const err = new Error("Network Error");
    expect(extractErrorMessage(err, "fallback")).toBe("Network Error");
  });

  it("falls back to the provided fallback for a non-Error, non-axios value", () => {
    expect(extractErrorMessage("some string", "fallback")).toBe("fallback");
    expect(extractErrorMessage(null, "fallback")).toBe("fallback");
    expect(extractErrorMessage(undefined, "fallback")).toBe("fallback");
  });

  it("falls back when response.data has no detail field", () => {
    const err = { response: { data: {} } };
    expect(extractErrorMessage(err, "fallback")).toBe("fallback");
  });

  it("falls back when response.data.detail is an empty string", () => {
    const err = { response: { data: { detail: "" } } };
    expect(extractErrorMessage(err, "fallback")).toBe("fallback");
  });
});
