import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PurchaseReceiving } from "./purchase-receiving";
import type { PurchaseOrder } from "./api";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  permissions: ["procurement.write"],
  activities: {
    items: [
      {
        id: "activity",
        occurred_at: "2026-09-06T08:00:00Z",
        summary: "purchase_order.receipt_recorded",
      },
    ],
  },
}));
vi.mock("../overview/session", () => ({ useSessionScope: () => "fixture" }));
vi.mock("../overview/api", () => ({
  useMemberContext: () => ({ data: { permissions: mocks.permissions } }),
}));
vi.mock("./api", () => ({
  usePurchaseReceiptCommand: () => ({ mutate: mocks.mutate, isPending: false }),
  usePurchaseActivities: () => ({ data: mocks.activities, refetch: vi.fn() }),
}));
afterEach(() => {
  cleanup();
  mocks.mutate.mockReset();
  mocks.permissions = ["procurement.write"];
});
const order = {
  id: "purchase",
  status: "CONFIRMED",
  version: 8,
  items: [
    {
      id: "line",
      sku_snapshot: "VALVE",
      quantity: "2.0000",
      received_quantity: "0.0000",
      unit_snapshot: "pcs",
    },
  ],
} as PurchaseOrder;

it("labels restricted operational history without requiring cost access", () => {
  mocks.permissions = ["procurement.read"];
  render(<PurchaseReceiving order={order} />);
  fireEvent.click(screen.getByRole("button", { name: "查看采购记录" }));
  expect(screen.getByText("已登记采购收货")).toBeInTheDocument();
  expect(
    screen.queryByText("purchase_order.receipt_recorded"),
  ).not.toBeInTheDocument();
});

it("validates empty receipt and sends decimal strings with version and retry key", async () => {
  render(<PurchaseReceiving order={order} />);
  fireEvent.click(screen.getByRole("button", { name: "记录收货" }));
  fireEvent.click(screen.getByRole("button", { name: "确认本次收货" }));
  expect(await screen.findByText("请填写收货凭证号或说明")).toBeInTheDocument();
  expect(mocks.mutate).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("收货凭证号或说明"), {
    target: { value: "R-1" },
  });
  fireEvent.change(screen.getByLabelText("收货日期"), {
    target: { value: "2026-09-05" },
  });
  fireEvent.change(screen.getByLabelText("VALVE 本次收货量"), {
    target: { value: "0.1001" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认本次收货" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
  expect(mocks.mutate.mock.calls[0][0]).toMatchObject({
    command: "receive",
    body: {
      expected_version: 8,
      reference: "R-1",
      items: [{ purchase_order_item_id: "line", quantity: "0.1001" }],
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认本次收货" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(2));
  expect(mocks.mutate.mock.calls[0][0].key).toBe(
    mocks.mutate.mock.calls[1][0].key,
  );
});
it("hides receipt commands without write permission", () => {
  mocks.permissions = [];
  render(<PurchaseReceiving order={order} />);
  expect(screen.getByText("当前成员无收货或关闭权限。")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "记录收货" }),
  ).not.toBeInTheDocument();
});
it("requires a close reason and distinguishes fulfillment from supplier payment", async () => {
  render(<PurchaseReceiving order={{ ...order, status: "RECEIVED" }} />);
  fireEvent.click(screen.getByRole("button", { name: "关闭采购单" }));
  expect(
    screen.getByText("关闭仅确认采购履约结束，不表示供应商款项已结清。"),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "确认关闭采购单" }));
  expect(await screen.findByText("请填写关闭原因")).toBeInTheDocument();
  expect(mocks.mutate).not.toHaveBeenCalled();
});

it("does not turn an open receipt into closure when refreshed data arrives before callbacks", () => {
  const view = render(<PurchaseReceiving order={order} />);
  fireEvent.click(screen.getByRole("button", { name: "记录收货" }));
  view.rerender(
    <PurchaseReceiving order={{ ...order, version: 9, status: "RECEIVED" }} />,
  );
  expect(
    screen.queryByRole("button", { name: "确认本次收货" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByLabelText("关闭原因")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "关闭采购单" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "关闭采购单" }));
  expect(screen.getByLabelText("关闭原因")).toBeInTheDocument();
});

it("requires reopening after a partial receipt refresh and hides stale closure on completion", () => {
  const view = render(<PurchaseReceiving order={order} />);
  fireEvent.click(screen.getByRole("button", { name: "记录收货" }));
  view.rerender(
    <PurchaseReceiving
      order={{ ...order, version: 9, status: "PARTIALLY_RECEIVED" }}
    />,
  );
  expect(screen.queryByLabelText("收货凭证号或说明")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "记录收货" })).toBeInTheDocument();
  view.rerender(
    <PurchaseReceiving order={{ ...order, version: 10, status: "RECEIVED" }} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "关闭采购单" }));
  view.rerender(
    <PurchaseReceiving order={{ ...order, version: 11, status: "CLOSED" }} />,
  );
  expect(screen.queryByLabelText("关闭原因")).not.toBeInTheDocument();
  expect(mocks.mutate).not.toHaveBeenCalled();
});
