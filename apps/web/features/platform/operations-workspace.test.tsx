import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { OperationsPanel, OperationsWorkspace } from "./operations-workspace";
import type { Operations } from "./operations-api";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});
it("keeps unknown costs, undecided approvals and absent process samples explicit", () => {
  render(
    <OperationsPanel
      data={
        {
          captured_at: "2026-09-06T00:00:00Z",
          scope: "current_organization",
          outbox_states: {},
          awaiting_consumer_count: 0,
          oldest_awaiting_seconds: null,
          job_states: {},
          document_states: {},
          ai_run_states: {},
          approval_states: {},
          approval_rate: null,
          ai_input_tokens: 0,
          ai_output_tokens: 0,
          known_estimated_cost_usd: "0",
          unknown_cost_runs: 2,
          request_metrics: null,
          latency_upper_bounds_ms: [],
          telemetry_scope: "current_api_process_since_bucket_creation",
        } satisfies Operations
      }
    />,
  );
  expect(screen.getByText("暂无已决请求")).toBeInTheDocument();
  expect(screen.getByText("当前进程尚无本组织运行样本。")).toBeInTheDocument();
  expect(
    screen.getByText("费用未知的运行数").nextElementSibling,
  ).toHaveTextContent("2");
});
it("does not request operational counters without explicit monitor permission", async () => {
  localStorage.setItem(
    "trade-workbench.organization-id",
    "00000000-0000-4000-8000-000000000001",
  );
  localStorage.setItem("trade-workbench.access-token", "test-token");
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ permissions: [] }), {
      headers: { "Content-Type": "application/json" },
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <OperationsWorkspace />
    </QueryClientProvider>,
  );
  expect(
    await screen.findByText("当前成员没有运行监控权限，请联系管理员。"),
  ).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(
    screen.queryByRole("button", { name: "刷新运行数据" }),
  ).not.toBeInTheDocument();
});
