import {
  fireEvent,
  render,
  screen,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ApiClientError, type components } from "@trade-workbench/api-client";
import { ResumeUpload } from "./resume-upload";

const mocks = vi.hoisted(() => ({ scope: "a:1", client: {}, resume: vi.fn() }));
vi.mock("../overview/session", () => ({
  useSessionScope: () => mocks.scope,
  sessionClient: () => mocks.client,
}));
vi.mock("./transfer", () => ({ resumeDocumentUpload: mocks.resume }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mocks.scope = "a:1";
});
const document = {
  id: "document",
  latest_version_number: 1,
  versions: [
    {
      id: "version",
      version_number: 1,
      status: "PENDING_UPLOAD",
      file_name: "proof.txt",
      expected_size_bytes: 5,
    },
  ],
} as components["schemas"]["DocumentResponse"];

it("validates input, shows mismatch inline and keeps selection for retry", async () => {
  const refreshed = vi.fn().mockResolvedValue(undefined);
  mocks.resume
    .mockRejectedValueOnce(
      new ApiClientError({
        code: "UPLOAD_FILE_MISMATCH",
      } as components["schemas"]["ProblemDetails"]),
    )
    .mockResolvedValueOnce({});
  render(<ResumeUpload document={document} onRecovered={refreshed} />);
  fireEvent.click(screen.getByRole("button", { name: "继续上传原文件" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "请选择原来的非空文件",
  );
  expect(mocks.resume).not.toHaveBeenCalled();
  const file = new File(["proof"], "proof.txt", { type: "text/plain" });
  fireEvent.change(screen.getByLabelText("重新选择原文件"), {
    target: { files: [file] },
  });
  fireEvent.click(screen.getByRole("button", { name: "继续上传原文件" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("文件不匹配");
  fireEvent.click(screen.getByRole("button", { name: "继续上传原文件" }));
  await waitFor(() => expect(refreshed).toHaveBeenCalledTimes(1));
  expect(mocks.resume).toHaveBeenLastCalledWith(
    mocks.client,
    "document",
    "version",
    file,
  );
});

it("disables in-flight controls and resets selected file on session change", async () => {
  let finish!: () => void;
  mocks.resume.mockReturnValueOnce(
    new Promise<void>((resolve) => {
      finish = resolve;
    }),
  );
  const props = { document, onRecovered: vi.fn().mockResolvedValue(undefined) };
  const view = render(<ResumeUpload {...props} />);
  fireEvent.change(screen.getByLabelText("重新选择原文件"), {
    target: { files: [new File(["proof"], "proof.txt")] },
  });
  fireEvent.click(screen.getByRole("button"));
  await waitFor(() => expect(screen.getByRole("button")).toBeDisabled());
  expect(screen.getByLabelText("重新选择原文件")).toBeDisabled();
  mocks.scope = "b:2";
  view.rerender(<ResumeUpload {...props} />);
  expect(screen.getByRole("button")).toBeEnabled();
  fireEvent.click(screen.getByRole("button"));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "请选择原来的非空文件",
  );
  finish();
  await waitFor(() => expect(props.onRecovered).toHaveBeenCalledTimes(1));
  expect(mocks.resume).toHaveBeenCalledTimes(1);
});

it("hides accepted and superseded pending versions", () => {
  const props = { onRecovered: vi.fn() };
  const view = render(
    <ResumeUpload
      {...props}
      document={{ ...document, latest_version_number: 2 }}
    />,
  );
  expect(screen.queryByRole("form")).toBeNull();
  view.rerender(
    <ResumeUpload
      {...props}
      document={{
        ...document,
        versions: document.versions!.map((v) => ({
          ...v,
          status: "AVAILABLE",
        })),
      }}
    />,
  );
  expect(screen.queryByRole("form")).toBeNull();
});
