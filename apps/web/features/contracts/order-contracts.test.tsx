import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { SalesOrder } from "../orders/api";
import { OrderContracts } from "./order-contracts";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});
function renderPanel(permissions: string[]) {
  localStorage.setItem(
    "trade-workbench.organization-id",
    "00000000-0000-4000-8000-000000000001",
  );
  localStorage.setItem("trade-workbench.access-token", "test-token");
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(
      async (input) =>
        new Response(
          JSON.stringify(
            new URL((input as Request).url).pathname.endsWith("/me/context")
              ? { permissions }
              : { items: [], has_more: false, next_cursor: null },
          ),
          { headers: { "Content-Type": "application/json" } },
        ),
    );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <OrderContracts
        order={
          {
            id: "00000000-0000-4000-8000-000000000701",
            status: "EXECUTING",
          } as SalesOrder
        }
      />
    </QueryClientProvider>,
  );
  return fetch;
}
it("does not fetch contracts without read permission", async () => {
  const fetch = renderPanel([]);
  await screen.findByText("当前成员无合同读取权限。");
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("shows read-only records without creation or upload controls", async () => {
  renderPanel(["contract.read", "document.read"]);
  await screen.findByText("此订单尚无合同记录。");
  expect(
    screen.queryByRole("button", { name: "建立合同草稿" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "上传合同证据" }),
  ).not.toBeInTheDocument();
});
