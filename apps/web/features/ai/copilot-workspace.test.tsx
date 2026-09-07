import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CopilotWorkspace } from "./copilot-workspace";

const state = vi.hoisted(() => ({
  scope: "org-session",
  permissions: ["ai.read", "ai.run", "order.read"],
  mutate: vi.fn(),
}));
vi.mock("../overview/session", () => ({
  useSessionScope: () => state.scope,
  disconnectSession: vi.fn(),
}));
vi.mock("../overview/api", () => ({
  useMemberContext: () => ({ data: { permissions: state.permissions } }),
}));
vi.mock("../overview/overview-workspace", () => ({
  WorkspaceConnection: () => <h1>连接业务空间</h1>,
}));
vi.mock("./api", () => ({
  useRuns: () => ({
    data: {
      items: [{ id: "run-1", intent: "TIMELINE", status: "FAILED" }],
      has_more: false,
    },
    refetch: vi.fn(),
  }),
  useRun: () => ({
    data: {
      id: "run-1",
      intent: "TIMELINE",
      status: "FAILED",
      model: "unconfigured",
      input_tokens: 0,
      output_tokens: 0,
      estimated_cost_usd: null,
      error_code: "AI_PROVIDER_NOT_CONFIGURED",
    },
  }),
  useCalls: () => ({ data: [] }),
  useApprovals: () => ({
    data: { items: [], has_more: false },
    refetch: vi.fn(),
  }),
  useAiCommand: () => ({ mutateAsync: state.mutate }),
}));
vi.mock("./disclosure-api", () => ({
  useDisclosures: () => ({
    data: { items: [], has_more: false },
    refetch: vi.fn(),
  }),
  useDisclosureCommand: () => ({ mutateAsync: state.mutate }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

describe("CopilotWorkspace", () => {
  beforeEach(() => {
    state.scope = "org-session";
    state.permissions = ["ai.read", "ai.run", "order.read"];
    state.mutate.mockReset();
  });
  afterEach(cleanup);
  it("requires a business session", () => {
    state.scope = "";
    render(<CopilotWorkspace />);
    expect(
      screen.getByRole("heading", { name: "连接业务空间" }),
    ).toBeInTheDocument();
  });
  it("hides commands and profit options without permissions", () => {
    state.permissions = ["ai.read"];
    render(<CopilotWorkspace />);
    expect(
      screen.queryByRole("button", { name: "开始辅助工作" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "人工审核任务建议" }),
    ).not.toBeInTheDocument();
  });
  it("clearly reports missing provider configuration instead of fabricated output", () => {
    render(<CopilotWorkspace />);
    fireEvent.click(
      screen.getByRole("button", { name: "摘要订单进度 · 未成功" }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "模型服务尚未配置，未生成结果",
    );
    expect(
      screen.queryByRole("heading", { name: "草稿 · 未发送、未执行" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: "解释报价毛利" }),
    ).not.toBeInTheDocument();
  });
  it("validates the selected order before submitting", async () => {
    render(<CopilotWorkspace />);
    fireEvent.change(screen.getByLabelText("订单 ID"), {
      target: { value: "not-an-order-id" },
    });
    fireEvent.click(screen.getByRole("button", { name: "开始辅助工作" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "请输入有效的订单 ID",
    );
    expect(state.mutate).not.toHaveBeenCalled();
  });
});
