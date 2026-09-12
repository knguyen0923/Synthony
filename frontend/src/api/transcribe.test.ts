import { describe, expect, it } from "vitest";
import { classifyLink } from "./transcribe";

describe("classifyLink", () => {
  it.each([
    ["https://www.youtube.com/watch?v=abc123", "youtube"],
    ["https://youtube.com/watch?v=abc123", "youtube"],
    ["https://music.youtube.com/watch?v=abc123", "youtube"],
    ["https://youtu.be/abc123", "youtube"],
  ])("classifies %s as youtube", (url) => {
    expect(classifyLink(url)).toBe("youtube");
  });

  it.each([
    ["https://open.spotify.com/track/abc123", "spotify"],
    ["https://spotify.com/track/abc123", "spotify"],
  ])("classifies %s as spotify", (url) => {
    expect(classifyLink(url)).toBe("spotify");
  });

  it("classifies an unrelated host as invalid", () => {
    expect(classifyLink("https://example.com/watch?v=abc123")).toBe("invalid");
  });

  it("classifies a lookalike hostname (not a real subdomain) as invalid", () => {
    expect(classifyLink("https://youtube.com.evil.example/watch")).toBe("invalid");
  });

  it("classifies unparsable text as invalid rather than throwing", () => {
    expect(classifyLink("not a url at all")).toBe("invalid");
  });

  it("is case-insensitive on hostname", () => {
    expect(classifyLink("https://WWW.YOUTUBE.COM/watch?v=abc123")).toBe("youtube");
  });
});
