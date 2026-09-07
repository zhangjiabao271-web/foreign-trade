import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DisclosureQueue, SubmitDisclosure } from "./disclosure-panel";

const state = vi.hoisted(() => ({
  mutate: vi.fn(),
  reviewer: false,
  isError: false,
}));
vi.mock("./disclosure-api", () => ({
  useDisclosureCommand: () => ({
    mutateAsync: state.mutate,
    isError: state.isError,
  }),
  useDisclosures: () => ({
    data: {
      has_more: false,
      items: [
        {
          id: "review-1",
          run_id: "run-1",
          revision: 2,
          version: 1,
          status: "PENDING",
          current: true,
          content_digest: state.reviewer ? "a".repeat(64) : null,
          candidate: state.reviewer
            ? {
                draft: "待核对草稿",
                inferences: ["待核对推断"],
                task_title: "待核对任务",
              }
            : null,
        },
      ],
    },
    refetch: vi.fn(),
  }),
}));
beforeEach(() => {
  state.mutate.mockReset();
  state.reviewer = false;
  state.isError = false;
});
afterEach(cleanup);

it("requires explicit submission consent and sends only the selected version", async () => {
  render(<SubmitDisclosure scope="session" id="run-1" version={4} />);
  expect(screen.getByRole("button", { name: "提交内容审核" })).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "提交内容审核" }));
  await waitFor(() =>
    expect(state.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "submit",
        id: "run-1",
        body: { expected_version: 4 },
      }),
    ),
  );
});

it("does not display candidate or reviewer controls for a protected owner", () => {
  render(<DisclosureQueue scope="session" reviewer={false} />);
  expect(screen.getByText("候选正文受保护。")).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "记录内容决定" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("待核对草稿")).not.toBeInTheDocument();
});

it("requires a content confirmation and does not use business execution actions", async () => {
  state.reviewer = true;
  render(<DisclosureQueue scope="session" reviewer />);
  fireEvent.change(screen.getByLabelText("内容审核理由"), {
    target: { value: "已核对完整候选" },
  });
  fireEvent.click(screen.getByRole("button", { name: "记录内容决定" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "请确认已经核对完整候选内容",
  );
  expect(state.mutate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.change(screen.getByLabelText("内容决定"), {
    target: { value: "release" },
  });
  fireEvent.click(screen.getByRole("button", { name: "记录内容决定" }));
  await waitFor(() =>
    expect(state.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "decide",
        body: expect.objectContaining({
          expected_version: 1,
          release: true,
          confirmed: true,
          content_digest: "a".repeat(64),
        }),
      }),
    ),
  );
});

it("saves edits as a pending candidate instead of silently approving edited text", async () => {
  state.reviewer = true;
  render(<DisclosureQueue scope="session" reviewer />);
  fireEvent.change(screen.getByLabelText("脱敏草稿"), {
    target: { value: "删去敏感内容后的草稿" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存新候选，重新审核" }));
  await waitFor(() =>
    expect(state.mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        action: "revise",
        body: expect.objectContaining({
          expected_version: 1,
          candidate: expect.objectContaining({ draft: "删去敏感内容后的草稿" }),
        }),
      }),
    ),
  );
});
