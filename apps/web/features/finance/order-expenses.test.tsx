import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { SalesOrder } from "../orders/api";
import { OrderExpenses } from "./order-expenses";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});
function panel(permissions: string[]) {
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
      <OrderExpenses
        order={
          {
            id: "00000000-0000-4000-8000-000000000701",
            status: "EXECUTING",
            confirmed_at: "2026-01-01",
            currency_code: "EUR",
          } as SalesOrder
        }
      />
    </QueryClientProvider>,
  );
  return fetch;
}
it("does not request expense data when permission is absent", async () => {
  const fetch = panel([]);
  await waitFor(() =>
    expect(screen.queryByText("正在确认费用权限…")).not.toBeInTheDocument(),
  );
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(
    screen.queryByRole("region", { name: "订单费用" }),
  ).not.toBeInTheDocument();
});
it("read-only expense permission neither fetches profit nor offers writes", async () => {
  const fetch = panel(["expense.read"]);
  await screen.findByText("尚无订单费用，请按已核对的凭证登记。");
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(
    screen.queryByRole("button", { name: "登记订单费用" }),
  ).not.toBeInTheDocument();
});
