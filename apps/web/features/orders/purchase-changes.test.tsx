import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PurchaseChanges } from "./purchase-changes";
import { sumCommitments } from "./amounts";
import type { PurchaseOrder } from "./api";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  permissions: ["procurement.approve", "profit.read"],
}));
vi.mock("../overview/session", () => ({ useSessionScope: () => "fixture" }));
vi.mock("../overview/api", () => ({
  useMemberContext: () => ({ data: { permissions: mocks.permissions } }),
}));
vi.mock("./api", () => ({
  usePurchaseChangeCommand: () => ({ mutate: mocks.mutate, isPending: false }),
}));
afterEach(() => {
  cleanup();
  mocks.mutate.mockReset();
  mocks.permissions = ["procurement.approve", "profit.read"];
});
const order = {
  id: "purchase",
  status: "CONFIRMED",
  version: 8,
  sales_order_id: "sales",
  supplier_company_id: "00000000-0000-4000-8000-000000000001",
  currency_code: "CNY",
  exchange_rate: "0.12500000",
  items: [
    {
      id: "line",
      sales_order_item_id: "sales-line",
      sku_snapshot: "VALVE",
      quantity: "2.0000",
      received_quantity: "0.5000",
      unit_cost: "4.0000",
      unit_snapshot: "pcs",
    },
  ],
} as PurchaseOrder;

it("requires reason and explicit confirmation and retains retry key", async () => {
  render(<PurchaseChanges order={order} />);
  fireEvent.click(screen.getByRole("button", { name: "取消未收货部分" }));
  fireEvent.click(screen.getByRole("button", { name: "确认取消未收货部分" }));
  expect(await screen.findByText("请填写取消或变更原因")).toBeInTheDocument();
  expect(mocks.mutate).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("取消或变更原因"), {
    target: { value: "Supplier released remaining quantity" },
  });
  fireEvent.change(screen.getByLabelText("供应商取消依据"), {
    target: { value: "ACK-1" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "确认取消未收货部分" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
  expect(mocks.mutate.mock.calls[0][0]).toMatchObject({
    command: "cancel",
    body: { expected_version: 8, supplier_reference: "ACK-1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认取消未收货部分" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(2));
  expect(mocks.mutate.mock.calls[0][0].key).toBe(
    mocks.mutate.mock.calls[1][0].key,
  );
});
it("sends a replacement draft request without changing original line snapshots", async () => {
  render(<PurchaseChanges order={order} />);
  fireEvent.click(screen.getByRole("button", { name: "变更采购" }));
  fireEvent.change(screen.getByLabelText("取消或变更原因"), {
    target: { value: "New remaining price" },
  });
  fireEvent.change(screen.getByLabelText("VALVE 替代数量"), {
    target: { value: "1.5000" },
  });
  fireEvent.change(screen.getByLabelText("VALVE 新采购单价"), {
    target: { value: "4.1234" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "确认变更并生成新草稿" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
  expect(mocks.mutate.mock.calls[0][0]).toMatchObject({
    command: "amend",
    body: {
      replacement: {
        sales_order_id: "sales",
        items: [
          {
            sales_order_item_id: "sales-line",
            quantity: "1.5000",
            unit_cost: "4.1234",
          },
        ],
      },
    },
  });
  expect(order.items![0].unit_cost).toBe("4.0000");
});
it("hides commands without permission or after terminal state", () => {
  mocks.permissions = [];
  const view = render(<PurchaseChanges order={order} />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  mocks.permissions = ["procurement.approve"];
  view.rerender(<PurchaseChanges order={order} />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  mocks.permissions = ["procurement.approve", "profit.read"];
  view.rerender(<PurchaseChanges order={{ ...order, status: "CANCELLED" }} />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
it("sums retained commitment strings without floating point loss", () => {
  expect(sumCommitments(["99999999999999.9999", "0.0001"])).toBe(
    "100000000000000.0000",
  );
  expect(sumCommitments(["0.1000", "0.2000"])).toBe("0.3000");
});

it("does not turn missing commitments into a partial or zero total", () => {
  expect(sumCommitments(["12.3400", null])).toBeNull();
  expect(sumCommitments([undefined, "12.3400"])).toBeNull();
  expect(sumCommitments([])).toBe("0.0000");
});
