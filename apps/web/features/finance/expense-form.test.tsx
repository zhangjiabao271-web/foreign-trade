import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ExpenseForm } from "./expense-form";
import type { Expense } from "./expense-api";

const original = {
  id: "00000000-0000-4000-8000-000000000701",
  version: 7,
  expense_number: "EX-001",
  category: "FREIGHT",
  cost_treatment: "ADDITIONAL",
  amount: "12.3456",
  currency_code: "EUR",
  exchange_rate: "1.00000000",
  incurred_on: "2026-01-01",
  description: "Carrier charge",
  evidence_reference: "INV-001",
} as Expense;
function panel(expense?: Expense) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { mutations: { retry: false } } })
      }
    >
      <ExpenseForm
        scope="test"
        orderId="00000000-0000-4000-8000-000000000702"
        currency="EUR"
        original={expense}
        onDone={vi.fn()}
        onCancel={vi.fn()}
      />
    </QueryClientProvider>,
  );
}
beforeEach(() =>
  localStorage.setItem(
    "trade-workbench.organization-id",
    "00000000-0000-4000-8000-000000000001",
  ),
);
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});
it("requires explicit cost classification and evidence before recording", async () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  panel();
  fireEvent.click(screen.getByRole("button", { name: "保存订单费用" }));
  expect(await screen.findByText("请选择费用成本归类")).toBeInTheDocument();
  expect(screen.getByText("凭证引用至少三个字符")).toBeInTheDocument();
  expect(screen.getByText("请确认费用归类及操作含义")).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});
it("reversal retains opening version and retry key, without sending original amounts", async () => {
  const posts: Request[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    posts.push((input as Request).clone());
    return new Response(
      JSON.stringify({
        type: "about:blank",
        title: "Unavailable",
        status: 503,
        code: "TEMPORARY",
        detail: "请重试费用操作",
        request_id: "test",
        errors: [],
      }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  });
  panel(original);
  fireEvent.change(screen.getByLabelText("费用操作原因"), {
    target: { value: "重复发票冲销" },
  });
  fireEvent.click(screen.getByLabelText("我确认全额冲销此费用"));
  fireEvent.click(screen.getByRole("button", { name: "确认冲销费用" }));
  await screen.findByText("请重试费用操作");
  fireEvent.click(screen.getByRole("button", { name: "确认冲销费用" }));
  await waitFor(() => expect(posts).toHaveLength(2));
  expect(posts[0]!.headers.get("Idempotency-Key")).toBe(
    posts[1]!.headers.get("Idempotency-Key"),
  );
  expect(await posts[0]!.json()).toEqual({
    expected_version: 7,
    reason: "重复发票冲销",
  });
});
