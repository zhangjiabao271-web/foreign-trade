import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SupplierForm } from "./supplier-form";
import { CatalogWorkspace } from "./catalog-workspace";
import type { SupplierLink } from "./api";
const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  pending: false,
  permissions: [
    "product.read",
    "profit.read",
    "product_supplier.read",
    "product_supplier.write",
  ],
}));
vi.mock("../overview/session", () => ({ useSessionScope: () => "fixture" }));
vi.mock("../overview/api", () => ({
  useMemberContext: () => ({ data: { permissions: mocks.permissions } }),
}));
vi.mock("../companies/api", () => ({
  useCompanies: () => ({ data: { items: [], has_more: false } }),
}));
vi.mock("./api", () => ({
  useWriteSupplier: () => ({ mutate: mocks.mutate, isPending: mocks.pending }),
  useProduct: () => ({
    data: { id: "product", name: "Product", sku: "SKU", unit: "set" },
  }),
  useProducts: () => ({ data: { items: [] } }),
  useSupplierLinks: () => ({ data: { items: [], has_more: false } }),
  useSupplierHistory: () => ({ data: { items: [], has_more: false } }),
}));
afterEach(() => {
  cleanup();
  mocks.mutate.mockReset();
  mocks.pending = false;
  mocks.permissions = [
    "product.read",
    "profit.read",
    "product_supplier.read",
    "product_supplier.write",
  ];
});
const row: SupplierLink = {
  id: "b4ba565b-d3f8-44de-92b5-f3a30f3c38c0",
  product_id: "e9f7d227-b646-4b4e-a739-4b00c8fc1b9b",
  supplier_id: "287f601d-c220-42a8-9e9b-49c5d654d9a6",
  supplier_name: "Supplier A",
  version: 3,
  created_at: "2026-09-06T00:00:00Z",
  supplier_sku: "FACTORY-1",
  unit_price: "7.7777",
  currency: "CNY",
  lead_time_days: 21,
  quoted_on: "2026-09-06",
  valid_until: "2026-10-06",
  quotation_reference: "RFQ",
};
it("keeps money as a string, identity and opening version, and reuses unchanged retry keys", async () => {
  render(
    <SupplierForm
      scope="fixture"
      productId={row.product_id}
      row={row}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "保存供应商参考" }));
  expect(await screen.findByText("请填写修改原因")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("修改原因"), {
    target: { value: "核对价格" },
  });
  fireEvent.change(screen.getByLabelText("参考单价"), {
    target: { value: "12345678901234.1234" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存供应商参考" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
  expect(mocks.mutate.mock.calls[0][0]).toMatchObject({
    kind: "update",
    linkId: row.id,
    body: {
      unit_price: "12345678901234.1234",
      expected_version: 3,
      reason: "核对价格",
    },
  });
  expect(mocks.mutate.mock.calls[0][0].body).not.toHaveProperty("supplier_id");
  fireEvent.click(screen.getByRole("button", { name: "保存供应商参考" }));
  await vi.waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(2));
  expect(mocks.mutate.mock.calls[1][0].key).toBe(
    mocks.mutate.mock.calls[0][0].key,
  );
});
it("rejects reversed dates, negative prices and fractional lead times", async () => {
  render(
    <SupplierForm
      scope="fixture"
      productId={row.product_id}
      row={row}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  fireEvent.change(screen.getByLabelText("修改原因"), {
    target: { value: "核对" },
  });
  fireEvent.change(screen.getByLabelText("参考单价"), {
    target: { value: "-1" },
  });
  fireEvent.change(screen.getByLabelText("参考交期（天）"), {
    target: { value: "1.5" },
  });
  fireEvent.change(screen.getByLabelText("有效截止日期（选填）"), {
    target: { value: "2026-09-01" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存供应商参考" }));
  expect(
    await screen.findByText("请输入非负价格，最多 14 位整数和 4 位小数"),
  ).toBeInTheDocument();
  expect(screen.getByText("请填写整数天数")).toBeInTheDocument();
  expect(screen.getByText("有效期不能早于报价日期")).toBeInTheDocument();
  expect(mocks.mutate).not.toHaveBeenCalled();
});
it("disables fields and cancellation while saving", () => {
  mocks.pending = true;
  render(
    <SupplierForm
      scope="fixture"
      productId={row.product_id}
      row={row}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("参考单价")).toBeDisabled();
  expect(screen.getByRole("button", { name: "取消编辑" })).toBeDisabled();
});
it("hides commands from finance readers and hides supplier prices from unauthorized members", () => {
  mocks.permissions = ["product.read", "profit.read", "product_supplier.read"];
  const view = render(<CatalogWorkspace id={row.product_id} />);
  expect(
    screen.queryByRole("button", { name: "关联供应商" }),
  ).not.toBeInTheDocument();
  mocks.permissions = [];
  view.rerender(<CatalogWorkspace id={row.product_id} />);
  expect(screen.getByText("当前成员无产品查看权限。")).toBeInTheDocument();
});

it("keeps product basics available without supplier price queries", () => {
  mocks.permissions = ["product.read"];
  render(<CatalogWorkspace id={row.product_id} />);
  expect(screen.getByRole("heading", { name: "Product" })).toBeInTheDocument();
  expect(
    screen.getByText(/当前成员无成本与供应商参考价格查看权限/),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "关联供应商" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "供应商参考时间线" }),
  ).not.toBeInTheDocument();
});
