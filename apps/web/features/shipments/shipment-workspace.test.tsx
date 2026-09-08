import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { sessionKeys } from "../leads/api";

import { ShipmentWorkspace } from "./shipment-workspace";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const shipmentId = "00000000-0000-4000-8000-000000000501";
const shipment = {
  id: shipmentId,
  version: 7,
  shipment_number: "SHP-2026-000001",
  status: "BOOKED",
  forwarder_company_id: "00000000-0000-4000-8000-000000000502",
  booking_reference: "BK-SHA-1001",
  planned_departure_date: "2026-09-15",
  planned_arrival_date: "2026-10-08",
  booked_at: "2026-09-04T08:00:00Z",
  ready_at: null,
  customs_at: null,
  departed_at: null,
  in_transit_at: null,
  arrived_at: null,
  delivered_at: null,
  created_at: "2026-09-04T07:00:00Z",
  missing_required_documents: ["COMMERCIAL_INVOICE", "PACKING_LIST"],
  items: [
    {
      id: "00000000-0000-4000-8000-000000000503",
      sales_order_item_id: "00000000-0000-4000-8000-000000000504",
      quantity: "1.0000",
    },
  ],
} as const;

const order = {
  id: "00000000-0000-4000-8000-000000000505",
  order_number: "SO-2026-000002",
  quotation_id: "00000000-0000-4000-8000-000000000506",
  quotation_version_id: "00000000-0000-4000-8000-000000000507",
  opportunity_id: "00000000-0000-4000-8000-000000000508",
  company_id: "00000000-0000-4000-8000-000000000509",
  status: "EXECUTING",
  currency_code: "USD",
  base_currency_code: "CNY",
  exchange_rate: "7.20000000",
  payment_terms: "30% deposit",
  delivery_terms: "FOB Shanghai",
  subtotal: "1000.0000",
  tax_amount: "0.0000",
  freight_amount: "0.0000",
  total: "1000.0000",
  total_cost: "700.0000",
  gross_profit: "300.0000",
  gross_margin: "0.3000",
  deposit_rate: "0.3000",
  deposit_amount: "300.0000",
  deposit_due_date: "2026-09-05",
  confirmed_at: "2026-09-04T06:00:00Z",
  created_at: "2026-09-04T05:00:00Z",
  items: [
    {
      id: "00000000-0000-4000-8000-000000000504",
      quotation_item_id: "00000000-0000-4000-8000-000000000510",
      line_number: 1,
      product_id: null,
      sku_snapshot: "VALVE-316L",
      description_snapshot: "316L sanitary valve",
      unit_snapshot: "set",
      quantity: "2.0000",
      unit_price: "500.0000",
      unit_cost: "350.0000",
      cost_currency: "USD",
      cost_exchange_rate: "1.00000000",
      tax_amount: "0.0000",
      freight_amount: "0.0000",
      allocated_cost: "0.0000",
      line_subtotal: "1000.0000",
      line_total: "1000.0000",
      line_cost: "700.0000",
      line_gross_profit: "300.0000",
    },
  ],
} as const;

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function sourceLines(sourceOrders: unknown[] = [order]) {
  const items = sourceOrders.flatMap((value) => {
    const source = value as typeof order;
    return source.items.map((item) => ({
      id: item.id,
      sales_order_id: source.id,
      order_number: source.order_number,
      order_status: source.status,
      sku_snapshot: item.sku_snapshot,
      description_snapshot: item.description_snapshot,
      unit_snapshot: item.unit_snapshot,
    }));
  });
  return { items, count: items.length };
}

function renderWorkspace(id?: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <ShipmentWorkspace initialShipmentId={id} />
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

function mockPlanning(
  permissions: string[],
  command?: (request: Request) => Promise<Response>,
  sourceOrders: unknown[] = [order],
) {
  window.localStorage.setItem(
    sessionKeys.organizationId,
    "00000000-0000-4000-8000-000000000001",
  );
  window.localStorage.setItem(sessionKeys.accessToken, "test-member");
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const request = input instanceof Request ? input : new Request(input);
    if (request.url.endsWith("/api/v1/me/context"))
      return jsonResponse({ permissions });
    if (request.url.endsWith("/source-lines"))
      return jsonResponse(sourceLines(sourceOrders));
    if (request.method === "POST" && command) return command(request);
    if (request.url.includes("/api/v1/documents?"))
      return jsonResponse({ items: [], count: 0 });
    if (request.url.endsWith(`/api/v1/shipments/${shipmentId}`))
      return jsonResponse({
        ...shipment,
        status: "PLANNING",
        booking_reference: null,
      });
    if (request.url.includes("/api/v1/sales-orders"))
      return jsonResponse({ items: sourceOrders, count: sourceOrders.length });
    return jsonResponse({ items: [shipment], count: 1 });
  });
}

describe("ShipmentWorkspace", () => {
  beforeEach(() => {
    window.localStorage.clear();
    push.mockReset();
    vi.restoreAllMocks();
  });

  afterEach(() => cleanup());

  it("reads old shipment sources directly and distinguishes protected prose from loading", async () => {
    const fetchMock = mockPlanning(["shipment.read", "order.read"]);
    const original = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (input, init) => {
      const request = input instanceof Request ? input : new Request(input);
      if (request.url.endsWith("/source-lines")) {
        const body = sourceLines();
        return jsonResponse({
          ...body,
          items: body.items.map((item) => ({
            ...item,
            description_snapshot: null,
          })),
        });
      }
      return original(input, init);
    });
    const { queryClient } = renderWorkspace(shipmentId);
    expect(await screen.findByText("订单原文未获审核开放")).toBeInTheDocument();
    expect(screen.getByText(order.order_number)).toBeInTheDocument();
    expect(screen.queryByText("订单快照读取中")).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        new Request(input).url.includes("/sales-orders"),
      ),
    ).toBe(false);
    const before = fetchMock.mock.calls.filter(([input]) =>
      new Request(input).url.endsWith("/source-lines"),
    ).length;
    await queryClient.invalidateQueries({ queryKey: ["sales-orders"] });
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([input]) =>
          new Request(input).url.endsWith("/source-lines"),
        ).length,
      ).toBeGreaterThan(before),
    );
  });

  it("retries unavailable direct source snapshots without loading order pages", async () => {
    const fetchMock = mockPlanning(["shipment.read", "order.read"]);
    const original = fetchMock.getMockImplementation()!;
    let failed = true;
    fetchMock.mockImplementation(async (input, init) => {
      const request = input instanceof Request ? input : new Request(input);
      if (request.url.endsWith("/source-lines") && failed)
        return jsonResponse({ detail: "Source unavailable" }, 503);
      return original(input, init);
    });
    renderWorkspace(shipmentId);
    const retry = await screen.findByRole("button", { name: "重试来源快照" });
    expect(screen.getByText("来源快照暂不可用")).toBeInTheDocument();
    failed = false;
    fireEvent.click(retry);
    expect(await screen.findByText(order.order_number)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "重试来源快照" }),
    ).not.toBeInTheDocument();
  });

  it("loads an older order into shipment selection without losing earlier quantities", async () => {
    const posted: unknown[] = [];
    const newer = {
      ...order,
      id: order.quotation_id,
      order_number: "SO-NEWER",
      items: [
        { ...order.items[0], id: order.company_id, sku_snapshot: "NEWER" },
      ],
    };
    const fetchMock = mockPlanning(["shipment.write"]);
    fetchMock.mockImplementation(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const url = new URL(request.url);
      if (url.pathname.endsWith("/me/context"))
        return jsonResponse({ permissions: ["shipment.write"] });
      if (request.method === "POST") {
        posted.push(await request.json());
        return jsonResponse({ status: 503 }, 503);
      }
      if (url.pathname.endsWith("/sales-orders")) {
        const cursor = url.searchParams.get("cursor");
        if (cursor) expect(cursor).toBe(newer.id);
        return jsonResponse({
          items: cursor ? [order] : [newer],
          count: 1,
          has_more: !cursor,
          next_cursor: cursor ? null : newer.id,
        });
      }
      return jsonResponse({ items: [], count: 0 });
    });
    renderWorkspace();
    fireEvent.click(
      await screen.findByRole("button", { name: "创建出运计划" }),
    );
    fireEvent.click(await screen.findByRole("checkbox"));
    fireEvent.change(screen.getByLabelText("NEWER 本次出运数量"), {
      target: { value: "0.2500" },
    });
    fireEvent.click(screen.getByRole("button", { name: "加载更多订单" }));
    await screen.findByText(order.order_number);
    expect(screen.getByLabelText("NEWER 本次出运数量")).toHaveValue("0.2500");
    fireEvent.click(screen.getAllByRole("checkbox")[1]);
    const quantity = screen.getByLabelText("VALVE-316L 本次出运数量");
    fireEvent.change(quantity, { target: { value: "0.5000" } });
    fireEvent.submit(quantity.closest("form")!);
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({
      items: [
        { sales_order_item_id: newer.items[0].id, quantity: "0.2500" },
        { sales_order_item_id: order.items[0].id, quantity: "0.5000" },
      ],
    });
  });

  it.each([
    ["book", "PLANNING", "记录已订舱"],
    ["ready", "BOOKED", "确认文件齐备"],
    ["enter-customs", "READY", "进入报关"],
    ["depart", "CUSTOMS", "确认离港"],
    ["start-transit", "DEPARTED", "开始在途运输"],
    ["arrive", "IN_TRANSIT", "确认到港"],
    ["deliver", "ARRIVED", "确认完成交付"],
  ])(
    "preserves the original %s request across refreshed versions",
    async (command, status, label) => {
      let version = 7;
      const requests: {
        key: string | null;
        body: { expected_version: number };
      }[] = [];
      localStorage.setItem(
        sessionKeys.organizationId,
        "00000000-0000-4000-8000-000000000001",
      );
      localStorage.setItem(sessionKeys.accessToken, "test-member");
      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const request = input instanceof Request ? input : new Request(input);
        if (request.url.endsWith("/api/v1/me/context"))
          return jsonResponse({ permissions: ["shipment.transition"] });
        if (request.method === "POST") {
          expect(request.url).toContain(`/shipments/${shipmentId}/${command}`);
          requests.push({
            key: request.headers.get("Idempotency-Key"),
            body: await request.json(),
          });
          throw new TypeError("Synthetic lost response");
        }
        if (request.url.endsWith(`/shipments/${shipmentId}`))
          return jsonResponse({ ...shipment, status, version });
        if (request.url.includes("/sales-orders"))
          return jsonResponse({ items: [order], count: 1 });
        if (request.url.includes("/documents?"))
          return jsonResponse({ items: [], count: 0 });
        return jsonResponse({
          items: [{ ...shipment, status, version }],
          count: 1,
        });
      });
      const view = renderWorkspace(shipmentId);
      await screen.findByRole("button", { name: label });
      if (command === "book") {
        fireEvent.change(screen.getByLabelText("订舱参考号 *"), {
          target: { value: "ORIGINAL-BOOKING" },
        });
        version = 8;
        await view.queryClient.invalidateQueries({
          queryKey: ["shipment", shipmentId],
        });
      }
      fireEvent.click(screen.getByRole("button", { name: label }));
      await screen.findByRole("button", { name: "原样重试出运操作" });
      version = 8;
      await view.queryClient.invalidateQueries({
        queryKey: ["shipment", shipmentId],
      });
      fireEvent.click(screen.getByRole("button", { name: "原样重试出运操作" }));
      await waitFor(() => expect(requests).toHaveLength(2));
      expect(requests[0].body.expected_version).toBe(7);
      expect(requests[0].key).toBeTruthy();
      expect(requests[1]).toEqual(requests[0]);
      await screen.findByRole("button", { name: "原样重试出运操作" });
      if (command === "book") {
        expect(screen.getByLabelText("订舱参考号 *")).toHaveValue(
          "ORIGINAL-BOOKING",
        );
        fireEvent.click(
          screen.getByRole("button", { name: "按当前版本重新填写订舱" }),
        );
        fireEvent.change(screen.getByLabelText("订舱参考号 *"), {
          target: { value: "ORIGINAL-BOOKING" },
        });
      }
      fireEvent.click(screen.getByRole("button", { name: label }));
      await waitFor(() => expect(requests).toHaveLength(3));
      expect(requests[2].body.expected_version).toBe(8);
      expect(requests[2].key).not.toBe(requests[0].key);
    },
  );

  it("rejects invalid test connection details without storing credentials", async () => {
    renderWorkspace();
    fireEvent.change(screen.getByLabelText("组织 ID"), {
      target: { value: "invalid" },
    });
    fireEvent.change(screen.getByLabelText("访问令牌"), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByRole("button", { name: "连接业务空间" }));
    expect(await screen.findByText("请输入有效的组织 ID")).toBeInTheDocument();
    expect(screen.getByText("请填写隔离测试访问凭证")).toBeInTheDocument();
    expect(screen.getByLabelText("组织 ID")).toHaveFocus();
    expect(localStorage.getItem(sessionKeys.organizationId)).toBeNull();
    expect(localStorage.getItem(sessionKeys.accessToken)).toBeNull();
  });

  it("validates missing and empty uploads before allocating any server session", async () => {
    const post = vi.fn();
    mockPlanning(["document.write"], post);
    renderWorkspace(shipmentId);
    const button = await screen.findByRole("button", { name: "上传文件" });
    fireEvent.click(button);
    expect(await screen.findByText("请选择一个文件")).toBeInTheDocument();
    const input = screen.getByLabelText("选择文件（最大 25 MB）");
    expect(input).toHaveFocus();
    fireEvent.change(input, {
      target: { files: [new File([], "empty.txt", { type: "text/plain" })] },
    });
    fireEvent.click(button);
    expect(
      await screen.findByText("文件不能为空，且不得超过 25 MB"),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("excludes deselected invalid lines from the actual creation payload", async () => {
    const bodies: unknown[] = [];
    mockPlanning(
      ["shipment.write"],
      async (request) => {
        bodies.push(await request.json());
        return jsonResponse({ status: 503 }, 503);
      },
      [
        {
          ...order,
          items: [
            ...order.items,
            {
              ...order.items[0],
              id: "00000000-0000-4000-8000-000000000599",
              sku_snapshot: "SECOND",
            },
          ],
        },
      ],
    );
    renderWorkspace();
    fireEvent.click(
      await screen.findByRole("button", { name: "创建出运计划" }),
    );
    const boxes = await screen.findAllByRole("checkbox");
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    const second = screen.getByLabelText("SECOND 本次出运数量");
    fireEvent.change(second, { target: { value: "bad" } });
    fireEvent.click(boxes[1]);
    fireEvent.submit(second.closest("form")!);
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({
      items: [{ sales_order_item_id: order.items[0].id, quantity: "2.0000" }],
    });
  });

  it("rejects invalid creation fields inline before calling the backend", async () => {
    const post = vi.fn();
    mockPlanning(["shipment.write"], post);
    renderWorkspace();
    fireEvent.click(
      await screen.findByRole("button", { name: "创建出运计划" }),
    );
    fireEvent.click(await screen.findByRole("checkbox"));
    const quantity = screen.getByLabelText("VALVE-316L 本次出运数量");
    fireEvent.change(quantity, { target: { value: "1e3" } });
    fireEvent.submit(quantity.closest("form")!);
    expect(
      await screen.findByText("请输入大于零的数量，最多四位小数"),
    ).toBeInTheDocument();
    expect(quantity).toHaveFocus();
    expect(quantity).toHaveAttribute("aria-invalid", "true");
    expect(post).not.toHaveBeenCalled();
  });

  it("retains creation keys for unchanged retries and rotates them after edits", async () => {
    const attempts: { key: string | null; body: unknown }[] = [];
    mockPlanning(["shipment.write"], async (request) => {
      attempts.push({
        key: request.headers.get("Idempotency-Key"),
        body: await request.json(),
      });
      return jsonResponse({ status: 503 }, 503);
    });
    renderWorkspace();
    fireEvent.click(
      await screen.findByRole("button", { name: "创建出运计划" }),
    );
    fireEvent.click(await screen.findByRole("checkbox"));
    const quantity = screen.getByLabelText("VALVE-316L 本次出运数量");
    fireEvent.change(quantity, { target: { value: "0.2500" } });
    const form = quantity.closest("form")!;
    fireEvent.submit(form);
    await screen.findByRole("alert");
    expect(quantity).toHaveValue("0.2500");
    fireEvent.submit(form);
    await waitFor(() => expect(attempts).toHaveLength(2));
    expect(attempts[0].key).toBeTruthy();
    expect(attempts[1]).toEqual(attempts[0]);
    await waitFor(() => expect(quantity).not.toBeDisabled());
    fireEvent.change(quantity, { target: { value: "0.5000" } });
    fireEvent.submit(form);
    await waitFor(() => expect(attempts).toHaveLength(3));
    expect(attempts[2].key).not.toBe(attempts[0].key);
  });

  it("hides all shipment writes for a read-only member", async () => {
    const fetchMock = mockPlanning(["shipment.read", "document.read"]);
    renderWorkspace(shipmentId);
    expect(
      await screen.findByText("当前为只读视图，出运节点由有权限的成员推进。"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "创建出运计划" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "记录已订舱" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "上传文件" }),
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([input]) => input instanceof Request && input.method === "POST",
      ),
    ).toBe(false);
  });

  it("validates booking reference inline and focuses invalid input without posting", async () => {
    const post = vi.fn();
    mockPlanning(["shipment.transition"], post);
    renderWorkspace(shipmentId);
    const button = await screen.findByRole("button", { name: "记录已订舱" });
    const input = screen.getByLabelText("订舱参考号 *");
    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.click(button);
    expect(await screen.findByText("请输入订舱参考号")).toBeInTheDocument();
    expect(input).toHaveFocus();
    fireEvent.change(input, { target: { value: "x".repeat(121) } });
    fireEvent.click(button);
    expect(
      await screen.findByText("订舱参考号最多 120 个字符"),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("retains failed booking input and sends the same trimmed reference on retry", async () => {
    const bodies: unknown[] = [];
    mockPlanning(["shipment.transition"], async (request) => {
      bodies.push(await request.json());
      return jsonResponse(
        {
          status: 409,
          type: "https://trade-workbench.local/problems/invalid-state-transition",
          title: "Invalid state transition",
          request_id: "shipment-test",
          errors: [],
          code: "INVALID_STATE_TRANSITION",
          detail: "请刷新后核对状态",
        },
        409,
      );
    });
    renderWorkspace(shipmentId);
    const button = await screen.findByRole("button", { name: "记录已订舱" });
    const input = screen.getByLabelText("订舱参考号 *");
    fireEvent.change(input, { target: { value: " BK-001 " } });
    fireEvent.click(button);
    expect(await screen.findByText(/请刷新后核对状态/)).toHaveAttribute(
      "role",
      "alert",
    );
    expect(input).toHaveValue(" BK-001 ");
    fireEvent.click(button);
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies).toEqual([
      { booking_reference: "BK-001", expected_version: 7 },
      { booking_reference: "BK-001", expected_version: 7 },
    ]);
  });

  it("disables booking fields during the pending command", async () => {
    let release: (response: Response) => void = () => {};
    mockPlanning(
      ["shipment.transition"],
      () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    );
    renderWorkspace(shipmentId);
    const button = await screen.findByRole("button", { name: "记录已订舱" });
    const input = screen.getByLabelText("订舱参考号 *");
    fireEvent.change(input, { target: { value: "BK-PENDING" } });
    fireEvent.click(button);
    await waitFor(() => expect(input).toBeDisabled());
    expect(screen.getByRole("button", { name: "正在记录…" })).toBeDisabled();
    release(jsonResponse({ ...shipment, status: "BOOKED" }));
    await waitFor(() => expect(input).not.toBeDisabled());
  });

  it("requires a scoped session before shipment data is requested", () => {
    renderWorkspace();
    expect(
      screen.getByRole("heading", { name: "连接你的业务空间" }),
    ).toBeInTheDocument();
  });

  it("shows the route and document gap before sending the ready command", async () => {
    window.localStorage.setItem(
      sessionKeys.organizationId,
      "00000000-0000-4000-8000-000000000001",
    );
    window.localStorage.setItem(sessionKeys.accessToken, "operations-token");
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input) => {
        const request = input instanceof Request ? input : new Request(input);
        if (request.url.endsWith("/api/v1/me/context")) {
          return jsonResponse({
            permissions: [
              "shipment.write",
              "shipment.transition",
              "document.write",
            ],
          });
        }
        if (request.method === "POST" && request.url.endsWith("/ready")) {
          return jsonResponse({
            ...shipment,
            status: "READY",
            ready_at: "2026-09-04T09:00:00Z",
            missing_required_documents: [],
          });
        }
        if (request.url.includes("/api/v1/documents?")) {
          return jsonResponse({ items: [], count: 0 });
        }
        if (request.url.endsWith(`/api/v1/shipments/${shipmentId}`)) {
          return jsonResponse(shipment);
        }
        if (request.url.includes("/api/v1/sales-orders")) {
          return jsonResponse({ items: [order], count: 1 });
        }
        if (request.url.endsWith("/source-lines"))
          return jsonResponse(sourceLines());
        return jsonResponse({ items: [shipment], count: 1 });
      });

    renderWorkspace(shipmentId);

    expect(await screen.findByText("SHP-2026-000001")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "出运进度" })).toBeInTheDocument();
    expect(screen.getByText("离港文件仍有缺口")).toBeInTheDocument();
    expect(screen.getByText("316L sanitary valve")).toBeInTheDocument();
    fireEvent.click(
      await screen.findByRole("button", { name: "确认文件齐备" }),
    );

    await waitFor(() => {
      const request = fetchMock.mock.calls
        .map(([input]) => (input instanceof Request ? input : undefined))
        .find(
          (candidate) =>
            candidate?.method === "POST" && candidate.url.endsWith("/ready"),
        );
      expect(request).toBeDefined();
      expect(request?.headers.get("Authorization")).toBe(
        "Bearer operations-token",
      );
    });
  });
});
