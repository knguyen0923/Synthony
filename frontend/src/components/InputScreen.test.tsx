import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InputScreen } from "./InputScreen";
import { transcribeFile, transcribeLink } from "../api/transcribe";
import { arrangeFile, arrangeLink } from "../api/arrange";

vi.mock("../api/transcribe", () => ({
  transcribeFile: vi.fn(),
  transcribeLink: vi.fn(),
}));
vi.mock("../api/arrange", () => ({
  arrangeFile: vi.fn(),
  arrangeLink: vi.fn(),
}));

vi.mock("./UploadForm", () => ({
  UploadForm: (props: { submitFile: unknown; submitLink: unknown }) => (
    <div
      data-testid="upload-form"
      data-submit-file={props.submitFile === transcribeFile ? "transcribeFile" : props.submitFile === arrangeFile ? "arrangeFile" : "unknown"}
      data-submit-link={props.submitLink === transcribeLink ? "transcribeLink" : props.submitLink === arrangeLink ? "arrangeLink" : "unknown"}
    />
  ),
}));
vi.mock("./QrScanButton", () => ({
  QrScanButton: (props: { submitLink: unknown }) => (
    <div
      data-testid="qr-scan-button"
      data-submit-link={props.submitLink === transcribeLink ? "transcribeLink" : props.submitLink === arrangeLink ? "arrangeLink" : "unknown"}
    />
  ),
}));

describe("InputScreen", () => {
  it("wires transcribe functions in Solo piano recording mode (the default)", () => {
    render(<InputScreen onSuccess={vi.fn()} />);

    expect(screen.getByTestId("upload-form")).toHaveAttribute("data-submit-file", "transcribeFile");
    expect(screen.getByTestId("upload-form")).toHaveAttribute("data-submit-link", "transcribeLink");
    expect(screen.getByTestId("qr-scan-button")).toHaveAttribute("data-submit-link", "transcribeLink");
  });

  it("wires arrange functions after switching to Any song mode", async () => {
    const user = userEvent.setup();
    render(<InputScreen onSuccess={vi.fn()} />);

    await user.click(screen.getByRole("tab", { name: "Any song" }));

    expect(screen.getByTestId("upload-form")).toHaveAttribute("data-submit-file", "arrangeFile");
    expect(screen.getByTestId("upload-form")).toHaveAttribute("data-submit-link", "arrangeLink");
    expect(screen.getByTestId("qr-scan-button")).toHaveAttribute("data-submit-link", "arrangeLink");
  });
});
