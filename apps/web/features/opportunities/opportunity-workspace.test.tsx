import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  OpportunityAction,
  OpportunityWorkspace,
} from "./opportunity-workspace";
import type { Opportunity } from "./api";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  permissions: ["opportunity.read", "opportunity.write"],
  status: "QUOTING",
  pending: false,
}));
vi.mock("../overview/session", () => ({ useSessionScope: () => "fixture" }));
vi.mock("../overview/api", () => ({
  useMemberContext: () => ({ data: { permissions: mocks.permissions } }),
}));
vi.mock("./api", () => ({
  useOpportunityCommand: () => ({
    mutate: mocks.mutate,
    isPending: mocks.pending,
  }),
  useOpportunity: () => ({
    data: {
      id: "record",
      name: "客户采购计划",
      status: mocks.status,
      version: 3,
    },
  }),
  useOpportunityHistory: () => ({ data: { items: [], has_more: false } }),
  useOpportunities: () => ({ data: { items: [], has_more: false } }),
}));
afterEach(() => {
  cleanup();
  mocks.mutate.mockReset();
  mocks.permissions = ["opportunity.read", "opportunity.write"];
  mocks.status = "QUOTING";
  mocks.pending = false;
});
const row = { id: "record", version: 3 } as Opportunity;
it("requires reason and confirmation and retains unchanged retry key", async () => {
  render(
    <OpportunityAction
      scope="fixture"
      row={row}
      command="mark-lost"
      onClose={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "确认丢单" }));
  expect(await screen.findByText("请填写处理原因")).toBeInTheDocument();
  expect(mocks.mutate).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("处理原因"), {
    target: { value: "客户项目取消" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "确认丢单" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
  expect(mocks.mutate.mock.calls[0][0]).toMatchObject({
    command: "mark-lost",
    body: { expected_version: 3, reason: "客户项目取消" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认丢单" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(2));
  expect(mocks.mutate.mock.calls[0][0].key).toBe(
    mocks.mutate.mock.calls[1][0].key,
  );
});
it("hides commands for readers and terminal opportunities", () => {
  mocks.permissions = ["opportunity.read"];
  const view = render(<OpportunityWorkspace id="record" />);
  expect(
    screen.queryByRole("button", { name: "标记丢单" }),
  ).not.toBeInTheDocument();
  mocks.permissions.push("opportunity.write");
  mocks.status = "WON";
  view.rerender(<OpportunityWorkspace id="record" />);
  expect(
    screen.queryByRole("button", { name: "标记丢单" }),
  ).not.toBeInTheDocument();
  mocks.status = "QUOTING";
  view.rerender(<OpportunityWorkspace id="record" />);
  expect(screen.getByRole("button", { name: "开始洽谈" })).toBeInTheDocument();
});
it("disables edits and cancellation while a command is pending", () => {
  mocks.pending = true;
  render(
    <OpportunityAction
      scope="fixture"
      row={row}
      command="mark-lost"
      onClose={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("处理原因")).toBeDisabled();
  expect(screen.getByRole("button", { name: "返回，不做变更" })).toBeDisabled();
});
