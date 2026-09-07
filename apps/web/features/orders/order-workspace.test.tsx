import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { sessionKeys } from "../leads/api";

import { OrderWorkspace } from "./order-workspace";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const orderId = "00000000-0000-4000-8000-000000000401";
const order = {
  id: orderId,
  version: 7,
  order_number: "SO-2026-000001",
  quotation_id: "00000000-0000-4000-8000-000000000402",
  quotation_version_id: "00000000-0000-4000-8000-000000000403",
  opportunity_id: "00000000-0000-4000-8000-000000000404",
  company_id: "00000000-0000-4000-8000-000000000405",
  status: "DRAFT",
  currency_code: "EUR",
  base_currency_code: "USD",
  exchange_rate: "1.08000000",
  payment_terms: "30% deposit",
  delivery_terms: "FOB Shanghai",
  subtotal: "100.0000",
  tax_amount: "5.0000",
  freight_amount: "5.0000",
  total: "110.0000",
  total_cost: "70.0000",
  gross_profit: "40.0000",
  gross_margin: "0.3636",
  deposit_rate: "0.3000",
  deposit_amount: "33.0000",
  deposit_due_date: "2026-09-12",
  confirmed_at: null,
  created_at: "2026-09-04T08:00:00Z",
  items: [
    {
      id: "00000000-0000-4000-8000-000000000406",
      quotation_item_id: "00000000-0000-4000-8000-000000000407",
      line_number: 1,
      product_id: "00000000-0000-4000-8000-000000000408",
      sku_snapshot: "PUMP-CN",
      description_snapshot: "316L sanitary pump",
      unit_snapshot: "set",
      quantity: "2.0000",
      unit_price: "50.0000",
      unit_cost: "240.0000",
      cost_currency: "CNY",
      cost_exchange_rate: "0.14583333",
      tax_amount: "5.0000",
      freight_amount: "5.0000",
      allocated_cost: "0.0000",
      line_subtotal: "100.0000",
      line_total: "110.0000",
      line_cost: "70.0000",
      line_gross_profit: "40.0000",
    },
  ],
} as const;

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderWorkspace(id?: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <OrderWorkspace initialOrderId={id} />
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

describe("OrderWorkspace", () => {
  beforeEach(() => {
    window.localStorage.clear();
    push.mockReset();
    vi.restoreAllMocks();
  });

  afterEach(() => cleanup());

  it("does not present a partial purchase commitment as a complete total", async () => {
    const fetchMock = mockWorkspace([
      "order.read",
      "procurement.read",
      "profit.read",
    ]);
    const baseline = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (...args) => {
      const request =
        args[0] instanceof Request ? args[0] : new Request(args[0]);
      const url = new URL(request.url);
      if (url.pathname.endsWith("/purchase-orders")) {
        expect(url.searchParams.get("sales_order_id")).toBe(order.id);
        const cursor = url.searchParams.get("cursor");
        return jsonResponse({
          items: [],
          count: 0,
          has_more: !cursor,
          next_cursor: cursor ? null : order.id,
        });
      }
      return baseline(...args);
    });
    renderWorkspace(orderId);
    await screen.findByText("采购清单尚未加载完整，暂不显示完整采购承诺合计。");
    const strip = screen.getByRole("region", {
      name: "客户承诺、定金与采购承诺",
    });
    expect(strip).toHaveTextContent("未提供");
    fireEvent.click(screen.getByRole("button", { name: "加载更多采购单" }));
    await waitFor(() =>
      expect(
        screen.queryByText("采购清单尚未加载完整，暂不显示完整采购承诺合计。"),
      ).not.toBeInTheDocument(),
    );
    expect(strip).not.toHaveTextContent("未提供");
  });

  it("retains the failed confirmation version and key through background refresh", async () => {
    window.localStorage.setItem(
      sessionKeys.organizationId,
      "00000000-0000-4000-8000-000000000001",
    );
    window.localStorage.setItem(sessionKeys.accessToken, "order-manager-token");
    let version = 7;
    const bodies: unknown[] = [];
    const keys: (string | null)[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input as Request;
      if (request.url.endsWith("/me/context"))
        return jsonResponse({ permissions: ["order.confirm"] });
      if (request.method === "POST") {
        bodies.push(await request.json());
        keys.push(request.headers.get("Idempotency-Key"));
        return jsonResponse(
          { status: 503, code: "UNAVAILABLE", detail: "结果未知" },
          503,
        );
      }
      if (request.url.endsWith(`/sales-orders/${orderId}`))
        return jsonResponse({ ...order, version });
      return jsonResponse({ items: [], count: 0 });
    });
    const view = renderWorkspace(orderId);
    fireEvent.click(
      await screen.findByRole("button", { name: "经理确认订单" }),
    );
    await screen.findByRole("button", { name: "原样重试订单确认" });
    version = 8;
    await view.queryClient.invalidateQueries({
      queryKey: ["sales-order", orderId],
    });
    fireEvent.click(screen.getByRole("button", { name: "原样重试订单确认" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies).toEqual([{ expected_version: 7 }, { expected_version: 7 }]);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
    await screen.findByRole("button", { name: "原样重试订单确认" });
    fireEvent.click(screen.getByRole("button", { name: "经理确认订单" }));
    await waitFor(() => expect(bodies).toHaveLength(3));
    expect(bodies[2]).toEqual({ expected_version: 8 });
    expect(keys[2]).not.toBe(keys[1]);
  });

  it("requires a scoped session before order data is requested", () => {
    renderWorkspace();
    expect(
      screen.getByRole("heading", { name: "连接你的业务空间" }),
    ).toBeInTheDocument();
  });

  it("shows commitment facts and sends the manager confirm command", async () => {
    window.localStorage.setItem(
      sessionKeys.organizationId,
      "00000000-0000-4000-8000-000000000001",
    );
    window.localStorage.setItem(sessionKeys.accessToken, "order-manager-token");
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input) => {
        const request = input instanceof Request ? input : new Request(input);
        if (request.url.endsWith("/api/v1/me/context")) {
          return jsonResponse({ permissions: ["order.confirm"] });
        }
        if (request.method === "POST") {
          return jsonResponse({
            ...order,
            status: "DEPOSIT_PENDING",
            confirmed_at: "2026-09-04T09:00:00Z",
          });
        }
        if (request.url.endsWith(`/api/v1/sales-orders/${orderId}`)) {
          return jsonResponse(order);
        }
        if (request.url.endsWith("/api/v1/purchase-orders?limit=100")) {
          return jsonResponse({ items: [], count: 0 });
        }
        return jsonResponse({ items: [order], count: 1 });
      });

    renderWorkspace(orderId);

    expect(
      await screen.findByRole("heading", { name: "SO-2026-000001" }),
    ).toBeInTheDocument();
    expect(screen.getByText("客户订单额")).toBeInTheDocument();
    expect(screen.getByText("约定定金")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "客户承诺、定金与采购承诺" }),
    ).toBeInTheDocument();
    expect(screen.getByText("316L sanitary pump")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "经理确认订单" }));

    await waitFor(() => {
      const request = fetchMock.mock.calls
        .map(([input]) => (input instanceof Request ? input : undefined))
        .find(
          (candidate) =>
            candidate?.method === "POST" && candidate.url.endsWith("/confirm"),
        );
      expect(request).toBeDefined();
      expect(request?.headers.get("Authorization")).toBe(
        "Bearer order-manager-token",
      );
    });
  });
});

function mockWorkspace(
  permissions: string[],
  current: Record<string, unknown> = order,
  purchases: Record<string, unknown>[] = [],
  post?: (request: Request) => Promise<Response>,
) {
  window.localStorage.setItem(
    sessionKeys.organizationId,
    "00000000-0000-4000-8000-000000000001",
  );
  window.localStorage.setItem(sessionKeys.accessToken, "local-form-test-only");
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const request = input instanceof Request ? input : new Request(input);
    if (request.url.endsWith("/api/v1/me/context"))
      return jsonResponse({ permissions });
    if (request.method === "POST")
      return post ? post(request) : jsonResponse(current, 201);
    if (request.url.endsWith(`/api/v1/sales-orders/${orderId}`))
      return jsonResponse(current);
    if (request.url.includes("/api/v1/purchase-orders?"))
      return jsonResponse({ items: purchases, count: purchases.length });
    return jsonResponse({ items: [current], count: 1 });
  });
}

describe("Order business forms", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
    push.mockReset();
  });
  afterEach(() => cleanup());

  it("retains loaded orders after a page error, retries the cursor and restarts explicitly", async () => {
    window.localStorage.setItem(sessionKeys.organizationId, order.company_id);
    window.localStorage.setItem(
      sessionKeys.accessToken,
      "local-form-test-only",
    );
    const older = {
      ...order,
      id: order.quotation_id,
      order_number: "SO-OLDER",
    };
    const cursors: (string | null)[] = [];
    let fail = true;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const url = new URL(request.url);
      if (url.pathname.endsWith("/me/context"))
        return jsonResponse({ permissions: ["order.read"] });
      if (url.pathname.endsWith("/sales-orders")) {
        const cursor = url.searchParams.get("cursor");
        cursors.push(cursor);
        if (cursor && fail) throw new TypeError("Synthetic page failure");
        return jsonResponse({
          items: cursor ? [older] : [order],
          count: 1,
          has_more: !cursor,
          next_cursor: cursor ? null : order.id,
        });
      }
      return jsonResponse({ items: [], count: 0 });
    });
    renderWorkspace();
    fireEvent.click(
      await screen.findByRole("button", { name: "加载更多订单" }),
    );
    await screen.findByText(/订单分页加载失败/);
    expect(screen.getByText(order.order_number)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新加载订单清单" }));
    await waitFor(() => expect(cursors).toEqual([null, order.id, null]));
    await waitFor(() =>
      expect(screen.queryByText(/订单分页加载失败/)).not.toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "加载更多订单" }));
    await screen.findByText(/订单分页加载失败/);
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "加载更多订单" }));
    await screen.findByText("SO-OLDER");
    expect(cursors).toEqual([null, order.id, null, order.id, order.id]);
    expect(
      screen.queryByRole("button", { name: "加载更多订单" }),
    ).not.toBeInTheDocument();
  });

  it.each(["approve", "send", "confirm"] as const)(
    "retains original %s variables across purchase refresh and uses fresh reviewed versions",
    async (action) => {
      const purchase = {
        id: "00000000-0000-4000-8000-000000000791",
        version: 7,
        sales_order_id: orderId,
        purchase_order_number: "PO-RETRY",
        status: { approve: "DRAFT", send: "APPROVED", confirm: "SENT" }[action],
        currency_code: "CNY",
        total: "10",
        total_order_currency: "1",
        retained_total_order_currency: "1",
        items: [],
      };
      const requests: { body: Record<string, unknown>; key: string | null }[] =
        [];
      mockWorkspace(
        ["procurement.write", "procurement.approve", "profit.read"],
        { ...order, status: "EXECUTING" },
        [purchase],
        async (request) => {
          requests.push({
            body: await request.json(),
            key: request.headers.get("Idempotency-Key"),
          });
          throw new TypeError("Synthetic lost response");
        },
      );
      const view = renderWorkspace(orderId);
      const label = {
        approve: "批准采购单",
        send: "记录已发送",
        confirm: "记录供应商确认",
      }[action];
      fireEvent.click(await screen.findByRole("button", { name: label }));
      if (action === "confirm") {
        fireEvent.change(screen.getByLabelText("供应商确认号"), {
          target: { value: "ORIGINAL-ACK" },
        });
        fireEvent.change(screen.getByLabelText(/预计交付日/), {
          target: { value: "2026-11-05" },
        });
        // Refetch before the first submit must not move the open human decision's version.
        purchase.version = 8;
        await view.queryClient.invalidateQueries({
          queryKey: ["purchase-orders"],
        });
        fireEvent.click(screen.getByRole("button", { name: "保存确认" }));
      }
      await screen.findByRole("button", { name: "原样重试采购操作" });
      purchase.version = 8;
      await view.queryClient.invalidateQueries({
        queryKey: ["purchase-orders"],
      });
      fireEvent.click(screen.getByRole("button", { name: "原样重试采购操作" }));
      await waitFor(() => expect(requests).toHaveLength(2));
      expect(requests[0].body.expected_version).toBe(7);
      expect(requests[1]).toEqual(requests[0]);
      expect(requests[0].key).toBeTruthy();
      await screen.findByRole("button", { name: "原样重试采购操作" });
      if (action === "confirm") {
        fireEvent.click(screen.getByRole("button", { name: "取消确认" }));
        fireEvent.click(screen.getByRole("button", { name: label }));
        fireEvent.click(screen.getByRole("button", { name: "保存确认" }));
      } else fireEvent.click(screen.getByRole("button", { name: label }));
      await waitFor(() => expect(requests).toHaveLength(3));
      expect(requests[2].body.expected_version).toBe(8);
      expect(requests[2].key).not.toBe(requests[1].key);
    },
  );

  it.each([false, true])(
    "hides order cost columns without permission (redacted=%s)",
    async (redacted) => {
      const current = redacted
        ? {
            ...order,
            total_cost: null,
            gross_profit: null,
            gross_margin: null,
            items: order.items.map((item) => ({
              ...item,
              unit_cost: null,
              cost_currency: null,
              cost_exchange_rate: null,
              allocated_cost: null,
              line_cost: null,
              line_gross_profit: null,
            })),
          }
        : order;
      mockWorkspace(["order.read"], current);
      renderWorkspace(orderId);
      await screen.findByText("316L sanitary pump");
      expect(
        screen.queryByRole("columnheader", { name: "预计成本" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("columnheader", { name: /^毛利$/ }),
      ).not.toBeInTheDocument();
      expect(
        screen.getByText("订单成本和毛利仅管理员、经理、财务可见。"),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("columnheader", { name: "售价" }),
      ).toBeInTheDocument();
    },
  );

  it("shows authorized order costs and never formats missing values as zero", async () => {
    mockWorkspace(["order.read", "profit.read"], {
      ...order,
      items: [{ ...order.items[0], line_cost: null }],
    });
    renderWorkspace(orderId);
    await screen.findByRole("columnheader", { name: "预计成本" });
    expect(
      screen.getByRole("columnheader", { name: /^毛利$/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "未提供" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: /40/ })).toBeInTheDocument();
  });

  it("keeps write controls absent for a read-only member", async () => {
    mockWorkspace([]);
    renderWorkspace(orderId);
    await screen.findByText("316L sanitary pump");
    expect(
      screen.queryByRole("button", { name: "从已接受报价建单" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "经理确认订单" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "创建采购单" }),
    ).not.toBeInTheDocument();
  });

  it("validates order inputs and freezes pending values without decimal conversion", async () => {
    let release!: (response: Response) => void;
    let submitted: unknown;
    const pending = new Promise<Response>((resolve) => {
      release = resolve;
    });
    mockWorkspace(["order.write"], order, [], async (request) => {
      submitted = await request.json();
      return pending;
    });
    renderWorkspace();
    fireEvent.click(
      await screen.findByRole("button", { name: "从已接受报价建单" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "从报价生成订单" }));
    expect(
      await screen.findByText("请输入有效的已接受报价 ID"),
    ).toBeInTheDocument();
    expect(submitted).toBeUndefined();
    fireEvent.change(screen.getByLabelText(/已接受报价 ID/), {
      target: { value: order.quotation_id },
    });
    fireEvent.change(screen.getByLabelText(/定金比例/), {
      target: { value: "0.1234" },
    });
    fireEvent.click(screen.getByRole("button", { name: "从报价生成订单" }));
    await waitFor(() =>
      expect(submitted).toEqual({
        quotation_id: order.quotation_id,
        deposit_rate: "0.1234",
        deposit_due_date: null,
      }),
    );
    expect(screen.getByLabelText(/定金比例/)).toBeDisabled();
    expect(screen.getByRole("button", { name: "取消" })).toBeDisabled();
    release(jsonResponse(order, 201));
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith(`/orders/${orderId}`),
    );
  });

  it("retains order creation identity on unchanged retry and rotates after editing", async () => {
    const bodies: unknown[] = [];
    const keys: (string | null)[] = [];
    mockWorkspace(["order.write"], order, [], async (request) => {
      bodies.push(await request.json());
      keys.push(request.headers.get("Idempotency-Key"));
      return jsonResponse(
        {
          type: "https://trade-workbench.local/problems/unavailable",
          title: "Unavailable",
          status: 503,
          code: "UNAVAILABLE",
          detail: "结果未知",
          request_id: "00000000-0000-4000-8000-000000000001",
          errors: [],
        },
        503,
      );
    });
    renderWorkspace();
    fireEvent.click(
      await screen.findByRole("button", { name: "从已接受报价建单" }),
    );
    fireEvent.change(screen.getByLabelText(/已接受报价 ID/), {
      target: { value: order.quotation_id },
    });
    const button = screen.getByRole("button", { name: "从报价生成订单" });
    await act(async () => {
      fireEvent.submit(button.closest("form")!);
      fireEvent.submit(button.closest("form")!);
    });
    await waitFor(() => expect(bodies).toHaveLength(1));
    await screen.findByText(/结果未知/);
    expect(screen.getByLabelText(/定金比例/)).toHaveValue("0.3000");
    expect(screen.getByText(/订单可能已生成/)).toBeInTheDocument();
    fireEvent.click(button);
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toEqual(bodies[0]);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
    await screen.findByText(/结果未知/);
    fireEvent.change(screen.getByLabelText(/定金比例/), {
      target: { value: "0.4000" },
    });
    fireEvent.click(button);
    await waitFor(() => expect(bodies).toHaveLength(3));
    expect(keys[2]).not.toBe(keys[1]);
    expect(bodies[2]).toMatchObject({ deposit_rate: "0.4000" });
  });

  it("retains exact purchase inputs on a rejected request", async () => {
    let submitted: unknown;
    mockWorkspace(
      ["procurement.write", "procurement.read", "profit.read"],
      { ...order, status: "EXECUTING" },
      [],
      async (request) => {
        submitted = await request.json();
        return jsonResponse(
          {
            status: 409,
            title: "Conflict",
            detail: "采购数量超过剩余承诺",
            code: "PURCHASE_CAPACITY_EXCEEDED",
            type: "https://trade-workbench.local/problems/purchase-capacity-exceeded",
            request_id: "00000000-0000-4000-8000-000000000001",
            errors: [],
          },
          409,
        );
      },
    );
    renderWorkspace(orderId);
    fireEvent.click(await screen.findByRole("button", { name: "创建采购单" }));
    fireEvent.change(screen.getByLabelText(/供应商公司 ID/), {
      target: { value: order.company_id },
    });
    fireEvent.change(screen.getByLabelText("PUMP-CN 采购数量"), {
      target: { value: "1.2345" },
    });
    fireEvent.change(screen.getByLabelText("PUMP-CN 采购单价"), {
      target: { value: "12345678901234.5678" },
    });
    fireEvent.change(screen.getByLabelText(/换算到订单币种汇率/), {
      target: { value: "0.12345678" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建采购草稿" }));
    expect(
      await screen.findByText(/PURCHASE_CAPACITY_EXCEEDED/),
    ).toBeInTheDocument();
    expect(submitted).toEqual({
      sales_order_id: order.id,
      supplier_company_id: order.company_id,
      currency_code: "CNY",
      exchange_rate: "0.12345678",
      items: [
        {
          sales_order_item_id: order.items[0].id,
          quantity: "1.2345",
          unit_cost: "12345678901234.5678",
        },
      ],
    });
    expect(screen.getByLabelText("PUMP-CN 采购单价")).toHaveValue(
      "12345678901234.5678",
    );
    expect(screen.getByRole("button", { name: "创建采购草稿" })).toBeEnabled();
  });

  it("does not offer new procurement on completed orders", async () => {
    mockWorkspace(["procurement.write", "profit.read"], {
      ...order,
      status: "COMPLETED",
    });
    renderWorkspace(orderId);
    await screen.findByText("316L sanitary pump");
    expect(
      screen.queryByRole("button", { name: "创建采购单" }),
    ).not.toBeInTheDocument();
  });

  it("hides purchase costs and pricing controls from operational members", async () => {
    mockWorkspace(
      ["procurement.write", "procurement.read", "procurement.approve"],
      { ...order, status: "EXECUTING" },
      [
        {
          id: "00000000-0000-4000-8000-000000000701",
          purchase_order_number: "PO-RESTRICTED",
          sales_order_id: orderId,
          status: "DRAFT",
          currency_code: "CNY",
          total: "9876.5432",
          total_order_currency: "1234.5678",
          retained_total_order_currency: "1234.5678",
          items: [],
        },
      ],
    );
    renderWorkspace(orderId);
    await screen.findByText("PO-RESTRICTED");
    expect(screen.queryByText("原采购额")).not.toBeInTheDocument();
    expect(screen.queryByText("订单币种折算")).not.toBeInTheDocument();
    expect(screen.queryByText(/9876\.5432|1234\.5678/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "创建采购单" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /审批采购|变更采购/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "采购金额仅管理员、经理、财务可见；可继续查看数量和交付进度。",
      ),
    ).toBeInTheDocument();
  });

  it("uses one command key for rapid same-form submissions before a response", async () => {
    const keys: (string | null)[] = [];
    let release!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      release = resolve;
    });
    mockWorkspace(
      ["procurement.write", "profit.read"],
      { ...order, status: "EXECUTING" },
      [],
      async (request) => {
        keys.push(request.headers.get("Idempotency-Key"));
        return pending;
      },
    );
    renderWorkspace(orderId);
    fireEvent.click(await screen.findByRole("button", { name: "创建采购单" }));
    fireEvent.change(screen.getByLabelText(/供应商公司 ID/), {
      target: { value: order.company_id },
    });
    const form = screen
      .getByRole("button", { name: "创建采购草稿" })
      .closest("form")!;
    await act(async () => {
      fireEvent.submit(form);
      fireEvent.submit(form);
    });
    expect(keys.length).toBeGreaterThan(0);
    expect(keys[0]).toBeTruthy();
    expect(new Set(keys).size).toBe(1);
    expect(screen.getByLabelText(/供应商公司 ID/)).toBeDisabled();
    release(jsonResponse({ id: orderId }, 201));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "创建采购草稿" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("reuses purchase retry keys for unchanged bodies and rotates them for changed input", async () => {
    const requests: { key: string | null; body: unknown }[] = [];
    mockWorkspace(
      ["procurement.write", "profit.read"],
      { ...order, status: "EXECUTING" },
      [],
      async (request) => {
        requests.push({
          key: request.headers.get("Idempotency-Key"),
          body: await request.json(),
        });
        if (requests.length < 4) throw new TypeError("Synthetic lost response");
        return jsonResponse({ id: order.id }, 201);
      },
    );
    renderWorkspace(orderId);
    fireEvent.click(await screen.findByRole("button", { name: "创建采购单" }));
    fireEvent.change(screen.getByLabelText(/供应商公司 ID/), {
      target: { value: order.company_id },
    });
    for (let attempt = 1; attempt <= 3; attempt++) {
      if (attempt === 3)
        fireEvent.change(screen.getByLabelText("PUMP-CN 采购单价"), {
          target: { value: "239.1234" },
        });
      fireEvent.click(screen.getByRole("button", { name: "创建采购草稿" }));
      await waitFor(() => expect(requests).toHaveLength(attempt));
      expect(
        await screen.findByText("服务暂时不可用，请检查连接后重试。"),
      ).toBeInTheDocument();
      await waitFor(() =>
        expect(
          screen.getByRole("button", { name: "创建采购草稿" }),
        ).toBeEnabled(),
      );
    }
    fireEvent.click(screen.getByRole("button", { name: "创建采购草稿" }));
    await waitFor(() => expect(requests).toHaveLength(4));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "创建采购草稿" }),
      ).not.toBeInTheDocument(),
    );
    expect(requests[0].key).toBeTruthy();
    expect(requests[0]).toEqual(requests[1]);
    expect(requests[2]).toEqual(requests[3]);
    expect(requests[2].key).not.toBe(requests[0].key);
  });

  it("validates supplier confirmation before sending the explicit command", async () => {
    let submitted: unknown;
    const purchase = {
      id: "00000000-0000-4000-8000-000000000701",
      version: 6,
      sales_order_id: orderId,
      purchase_order_number: "PO-2026-000001",
      status: "SENT",
      currency_code: "CNY",
      total: "10.0000",
      total_order_currency: "1.0000",
      retained_total: "10.0000",
      retained_total_order_currency: "1.0000",
      expected_delivery_date: null,
      items: [],
    };
    mockWorkspace(
      ["procurement.write"],
      { ...order, status: "EXECUTING" },
      [purchase],
      async (request) => {
        expect(request.url).toContain(
          `/purchase-orders/${purchase.id}/confirm`,
        );
        submitted = await request.json();
        return jsonResponse({ ...purchase, status: "CONFIRMED" });
      },
    );
    renderWorkspace(orderId);
    fireEvent.click(
      await screen.findByRole("button", { name: "记录供应商确认" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "保存确认" }));
    expect(
      await screen.findByText("请选择有效的预计交付日"),
    ).toBeInTheDocument();
    expect(submitted).toBeUndefined();
    fireEvent.change(screen.getByLabelText(/预计交付日/), {
      target: { value: "2026-09-20" },
    });
    fireEvent.change(screen.getByLabelText("供应商确认号"), {
      target: { value: "PO-ACK-20" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存确认" }));
    await waitFor(() =>
      expect(submitted).toEqual({
        expected_version: 6,
        supplier_reference: "PO-ACK-20",
        expected_delivery_date: "2026-09-20",
      }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "保存确认" }),
      ).not.toBeInTheDocument(),
    );
  });
});
