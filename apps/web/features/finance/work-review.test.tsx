import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { WorkTextReview } from "./work-review";
import type { ComponentProps } from "react";

const mocks = vi.hoisted(() => ({
  permissions: ["order.read", "task.read", "profit.read"],
  scope: "organization:1",
  get: vi.fn(),
  post: vi.fn(),
}));
vi.mock("../overview/api", () => ({
  useMemberContext: () => ({ data: { permissions: mocks.permissions } }),
}));
vi.mock("../overview/session", () => ({
  useSessionScope: () => mocks.scope,
  sessionClient: () => ({ GET: mocks.get, POST: mocks.post }),
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  mocks.permissions = ["order.read", "task.read", "profit.read"];
  mocks.scope = "organization:1";
});
const snapshot = {
  record_id: "task-1",
  kind: "task",
  text: "Review this exact note",
  details: { note: "delivery checked" },
  version_id: "version-1",
  version: 4,
  content_digest: "a".repeat(64),
  released: false,
};

type WithoutCallback<T> = T extends unknown ? Omit<T, "onChanged"> : never;

function setup(
  target: WithoutCallback<ComponentProps<typeof WorkTextReview>> = {
    orderId: "order-1",
    kind: "task",
    recordId: "task-1",
  },
) {
  mocks.get.mockResolvedValue({ data: snapshot });
  const changed = vi.fn().mockResolvedValue(undefined);
  const view = render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <WorkTextReview {...target} onChanged={changed} />
    </QueryClientProvider>,
  );
  return { ...view, changed };
}

it("does not fetch review facts or expose approval controls without cost authority", () => {
  mocks.permissions = ["order.read", "task.read"];
  setup();
  expect(screen.queryByText("审核文本开放范围")).toBeNull();
  expect(mocks.get).not.toHaveBeenCalled();
});

it("hides the cached review snapshot after a failed authority refresh", async () => {
  setup();
  fireEvent.click(screen.getByText("审核文本开放范围"));
  await screen.findByText("Review this exact note");
  mocks.get.mockRejectedValue(new Error("Forbidden"));
  fireEvent.click(screen.getByRole("button", { name: "刷新待审核文本" }));
  await screen.findByText("无法读取文本，请检查权限或重试。");
  expect(screen.queryByText("Review this exact note")).toBeNull();
  expect(screen.queryByRole("button", { name: "确认文本审核" })).toBeNull();
});

it.each([
  ["lead", "lead.read"],
  ["company", "company.read"],
  ["opportunity", "opportunity.read"],
  ["customs_declaration", "export.read"],
  ["tax_refund_case", "export.read"],
  ["quotation", "quotation.read"],
  ["shipment", "shipment.read"],
] as const)(
  "reviews %s through its own authority and exact activity route",
  async (subjectType, permission) => {
    mocks.permissions = ["profit.read", permission];
    setup({
      subjectType,
      subjectId: "owner-1",
      recordId: "activity-1",
    });
    fireEvent.click(screen.getByText("审核文本开放范围"));
    await screen.findByRole("button", { name: "确认文本审核" });
    const route =
      "/api/v1/work/{subject_type}/{subject_id}/activities/{record_id}/review";
    const path = {
      subject_type: subjectType,
      subject_id: "owner-1",
      record_id: "activity-1",
    };
    expect(mocks.get).toHaveBeenCalledWith(route, { params: { path } });
    fireEvent.change(screen.getByLabelText("审核决定"), {
      target: { value: "restrict" },
    });
    fireEvent.change(screen.getByLabelText("审核说明"), {
      target: { value: "审核后保留内部资料" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    mocks.post.mockResolvedValue({ data: snapshot });
    fireEvent.click(screen.getByRole("button", { name: "确认文本审核" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalled());
    expect(mocks.post.mock.calls[0][0]).toBe(route);
    expect(mocks.post.mock.calls[0][1].params.path).toEqual(path);
  },
);

it("requires original company read permission even for a cost reviewer", () => {
  mocks.permissions = ["profit.read", "order.read"];
  setup({
    subjectType: "company",
    subjectId: "owner-1",
    recordId: "activity-1",
  });
  expect(screen.queryByText("审核文本开放范围")).toBeNull();
  expect(mocks.get).not.toHaveBeenCalled();
});

it.each(["lead", "opportunity"] as const)(
  "routes %s source text review separately from its activity history",
  async (crmKind) => {
    mocks.permissions = ["profit.read", `${crmKind}.read`];
    setup({ crmKind, recordId: "record-1" });
    fireEvent.click(screen.getByText("审核文本开放范围"));
    await screen.findByRole("button", { name: "确认文本审核" });
    const route = "/api/v1/crm-text/{kind}/{record_id}/review";
    const path = { kind: crmKind, record_id: "record-1" };
    expect(mocks.get).toHaveBeenCalledWith(route, { params: { path } });
    fireEvent.change(screen.getByLabelText("审核决定"), {
      target: { value: "release" },
    });
    fireEvent.change(screen.getByLabelText("审核说明"), {
      target: { value: "已核对本次全部原始正文" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    mocks.post.mockResolvedValue({ data: { ...snapshot, released: true } });
    fireEvent.click(screen.getByRole("button", { name: "确认文本审核" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalled());
    expect(mocks.post.mock.calls[0][0]).toBe(route);
    expect(mocks.post.mock.calls[0][1].params.path).toEqual(path);
  },
);

it.each(["customs", "refund"] as const)(
  "routes %s source review independently",
  async (exportKind) => {
    mocks.permissions = ["profit.read", "export.read"];
    setup({ exportKind, recordId: "case-1" });
    fireEvent.click(screen.getByText("审核文本开放范围"));
    await screen.findByRole("button", { name: "确认文本审核" });
    const route = "/api/v1/export-text/{kind}/{record_id}/review";
    const path = { kind: exportKind, record_id: "case-1" };
    expect(mocks.get).toHaveBeenCalledWith(route, { params: { path } });
    fireEvent.change(screen.getByLabelText("审核决定"), {
      target: { value: "release" },
    });
    fireEvent.change(screen.getByLabelText("审核说明"), {
      target: { value: "已审核案件全部备注与原因" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    mocks.post.mockResolvedValue({ data: { ...snapshot, released: true } });
    fireEvent.click(screen.getByRole("button", { name: "确认文本审核" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalled());
    expect(mocks.post.mock.calls[0][0]).toBe(route);
    expect(mocks.post.mock.calls[0][1].params.path).toEqual(path);
  },
);

it.each([
  {
    target: { sourceKind: "product" as const, recordId: "source-1" },
    permission: "product.read",
    route: "/api/v1/products/{record_id}/text-review",
    path: { record_id: "source-1" },
  },
  {
    target: { sourceKind: "inquiry" as const, recordId: "source-1" },
    permission: "inquiry.read",
    route: "/api/v1/inquiries/{record_id}/text-review",
    path: { record_id: "source-1" },
  },
  {
    target: { sourceKind: "purchase" as const, recordId: "source-1" },
    permission: "procurement.read",
    route: "/api/v1/purchase-orders/{record_id}/text-review",
    path: { record_id: "source-1" },
  },
  {
    target: {
      subjectType: "purchase_order" as const,
      subjectId: "purchase-1",
      recordId: "source-1",
    },
    permission: "procurement.read",
    route:
      "/api/v1/work/{subject_type}/{subject_id}/activities/{record_id}/review",
    path: {
      subject_type: "purchase_order",
      subject_id: "purchase-1",
      record_id: "source-1",
    },
  },
  ...(["quotation_version", "sales_order", "sales_contract"] as const).map(
    (kind, index) => ({
      target: { commercialKind: kind, recordId: "source-1" },
      permission: ["quotation.read", "order.read", "contract.read"][index],
      route: "/api/v1/commercial-text/{kind}/{record_id}/review",
      path: { kind, record_id: "source-1" },
    }),
  ),
])(
  "routes independent source review $permission",
  async ({ target, permission, route, path }) => {
    mocks.permissions = ["profit.read", permission];
    setup(target);
    fireEvent.click(screen.getByText("审核文本开放范围"));
    await screen.findByRole("button", { name: "确认文本审核" });
    expect(mocks.get).toHaveBeenCalledWith(route, { params: { path } });
    fireEvent.change(screen.getByLabelText("审核决定"), {
      target: { value: "release" },
    });
    fireEvent.change(screen.getByLabelText("审核说明"), {
      target: { value: "已核对本份全部商业正文" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    mocks.post.mockResolvedValue({ data: { ...snapshot, released: true } });
    fireEvent.click(screen.getByRole("button", { name: "确认文本审核" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalled());
    expect(mocks.post.mock.calls[0][0]).toBe(route);
    expect(mocks.post.mock.calls[0][1].params.path).toEqual(path);
  },
);

it("routes payment notes to an independent review with original read permission", async () => {
  mocks.permissions = ["profit.read", "payment.read"];
  setup({ paymentText: true, recordId: "payment-1" });
  fireEvent.click(screen.getByText("审核文本开放范围"));
  await screen.findByRole("button", { name: "确认文本审核" });
  const route = "/api/v1/payments/{payment_id}/text-review";
  expect(mocks.get).toHaveBeenCalledWith(route, {
    params: { path: { payment_id: "payment-1" } },
  });
  fireEvent.change(screen.getByLabelText("审核决定"), {
    target: { value: "release" },
  });
  fireEvent.change(screen.getByLabelText("审核说明"), {
    target: { value: "已核对全部收款备注" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  mocks.post.mockResolvedValue({ data: { ...snapshot, released: true } });
  fireEvent.click(screen.getByRole("button", { name: "确认文本审核" }));
  await waitFor(() => expect(mocks.post).toHaveBeenCalled());
  expect(mocks.post.mock.calls[0][0]).toBe(route);
  expect(mocks.post.mock.calls[0][1].params.path).toEqual({
    payment_id: "payment-1",
  });
});

it("requires an explicit decision and preserves the exact request key after a failed submission", async () => {
  const { changed } = setup();
  fireEvent.click(screen.getByText("审核文本开放范围"));
  fireEvent.click(await screen.findByRole("button", { name: "确认文本审核" }));
  await screen.findByText("请选择开放或保密。");
  expect(mocks.post).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("审核决定"), {
    target: { value: "release" },
  });
  fireEvent.change(screen.getByLabelText("审核说明"), {
    target: { value: "已核对文件不含内部成本" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  mocks.post
    .mockRejectedValueOnce(new Error("lost response"))
    .mockResolvedValueOnce({ data: { ...snapshot, released: true } });
  fireEvent.click(screen.getByRole("button", { name: "确认文本审核" }));
  await screen.findByText(/审核未确认完成/);
  fireEvent.click(screen.getByRole("button", { name: "确认文本审核" }));
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  expect(mocks.post).toHaveBeenCalledTimes(2);
  expect(mocks.post.mock.calls[0]).toEqual(mocks.post.mock.calls[1]);
  expect(mocks.post.mock.calls[0][1].body).toMatchObject({
    expected_version: 4,
    content_digest: snapshot.content_digest,
    release: true,
    confirmed: true,
  });
});

it("disables decision controls while a review is being recorded", async () => {
  setup();
  fireEvent.click(screen.getByText("审核文本开放范围"));
  await screen.findByRole("button", { name: "确认文本审核" });
  fireEvent.change(screen.getByLabelText("审核决定"), {
    target: { value: "restrict" },
  });
  fireEvent.change(screen.getByLabelText("审核说明"), {
    target: { value: "需要保留内部资料" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  let finish!: () => void;
  mocks.post.mockReturnValue(
    new Promise((resolve) => {
      finish = () => resolve({ data: snapshot });
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "确认文本审核" }));
  await waitFor(() => expect(screen.getByLabelText("审核决定")).toBeDisabled());
  expect(screen.getByLabelText("审核说明")).toBeDisabled();
  finish();
  await waitFor(() => expect(screen.getByLabelText("审核决定")).toBeEnabled());
});
