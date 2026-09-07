import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { PurchaseOrder } from "../orders/api";
import { SupplierForm, type SupplierEdit } from "./supplier-form";
import { PurchaseFinance } from "./purchase-finance";
import type { SupplierPayment } from "./supplier-api";

const purchase = {
  id: "00000000-0000-4000-8000-000000000701",
  purchase_order_number: "PO-001",
  currency_code: "CNY",
  supplier_company_id: "00000000-0000-4000-8000-000000000702",
  confirmed_at: "2026-01-01",
} as PurchaseOrder;
function form(edit: SupplierEdit) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { mutations: { retry: false } } })
      }
    >
      <SupplierForm
        scope="test"
        purchase={purchase}
        edit={edit}
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
it("requires payable evidence, dates, positive amount and explicit confirmation", async () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  form({ mode: "payable", choices: [] });
  fireEvent.click(screen.getByRole("button", { name: "保存供应商应付" }));
  expect(await screen.findByText("请选择应付到期日")).toBeInTheDocument();
  expect(screen.getByText("请填写至少三个字符的凭证引用")).toBeInTheDocument();
  expect(
    screen.getByText("请输入大于零且最多四位小数的金额"),
  ).toBeInTheDocument();
  expect(screen.getByText("请核对凭证并确认操作含义")).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});
it("retains opening payment version and key for unchanged reversal retries", async () => {
  const requests: Request[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    requests.push((input as Request).clone());
    return new Response(
      JSON.stringify({
        type: "about:blank",
        title: "Unavailable",
        status: 503,
        code: "TEMPORARY",
        detail: "请重试供应商操作",
        request_id: "test",
        errors: [],
      }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  });
  form({
    mode: "reverse",
    choices: [],
    payment: {
      id: purchase.id,
      version: 7,
      payment_number: "SP-001",
      currency_code: "CNY",
      available_amount: "0.0000",
    } as SupplierPayment,
  });
  fireEvent.change(screen.getByLabelText("供应商结算操作原因"), {
    target: { value: "错误凭证更正" },
  });
  fireEvent.click(screen.getByLabelText("我已核对供应商凭证并确认本次操作"));
  fireEvent.click(screen.getByRole("button", { name: "确认冲销供应商付款" }));
  await screen.findByText("请重试供应商操作");
  fireEvent.click(screen.getByRole("button", { name: "确认冲销供应商付款" }));
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests[0]!.headers.get("Idempotency-Key")).toBe(
    requests[1]!.headers.get("Idempotency-Key"),
  );
  expect(await requests[0]!.json()).toEqual({
    expected_version: 7,
    reason: "错误凭证更正",
  });
});
it("does not fetch supplier money or show controls without financial read permissions", async () => {
  localStorage.setItem("trade-workbench.access-token", "test-token");
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ permissions: [] }), {
      headers: { "Content-Type": "application/json" },
    }),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <PurchaseFinance purchase={purchase} />
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(
      screen.queryByText("正在确认供应商结算权限…"),
    ).not.toBeInTheDocument(),
  );
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(
    screen.queryByRole("button", { name: "查看供应商结算" }),
  ).not.toBeInTheDocument();
});
