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

import { QuotationWorkspace } from "./quotation-workspace";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const quotationId = "00000000-0000-4000-8000-000000000301";
const versionId = "00000000-0000-4000-8000-000000000302";

const version = {
  id: versionId,
  version: 7,
  quotation_id: quotationId,
  version_number: 2,
  status: "DRAFT",
  is_current: true,
  currency_code: "EUR",
  base_currency_code: "USD",
  exchange_rate: "1.08000000",
  valid_until: "2026-10-04",
  payment_terms: "30% deposit",
  delivery_terms: "FOB Shanghai",
  subtotal: "100.0000",
  tax_amount: "5.0000",
  freight_amount: "5.0000",
  total: "110.0000",
  total_cost: "70.0000",
  gross_profit: "40.0000",
  gross_margin: "0.3636",
  submitted_at: null,
  approved_at: null,
  approved_by: null,
  sent_at: null,
  accepted_at: null,
  items: [
    {
      id: "00000000-0000-4000-8000-000000000303",
      line_number: 1,
      product_id: "00000000-0000-4000-8000-000000000304",
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

const quotation = {
  id: quotationId,
  quotation_number: "Q-2026-000001",
  inquiry_id: "00000000-0000-4000-8000-000000000305",
  opportunity_id: "00000000-0000-4000-8000-000000000306",
  company_id: "00000000-0000-4000-8000-000000000307",
  accepted_version_id: null,
  current_version: version,
  versions: [version],
  created_at: "2026-09-04T08:00:00Z",
};

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
      <QuotationWorkspace initialQuotationId={id} />
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

describe("QuotationWorkspace", () => {
  beforeEach(() => {
    window.localStorage.clear();
    push.mockReset();
    vi.restoreAllMocks();
  });

  afterEach(() => cleanup());

  it("keeps a failed decision's version and key across a background revision", async () => {
    window.localStorage.setItem(
      sessionKeys.organizationId,
      "00000000-0000-4000-8000-000000000001",
    );
    window.localStorage.setItem(sessionKeys.accessToken, "quotation-token");
    const bodies: unknown[] = [];
    const keys: (string | null)[] = [];
    let refreshed = false;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input as Request;
      if (request.url.endsWith("/me/context"))
        return jsonResponse({ permissions: ["quotation.submit"] });
      if (request.method === "POST") {
        bodies.push(await request.json());
        keys.push(request.headers.get("Idempotency-Key"));
        return jsonResponse(
          { status: 503, code: "UNAVAILABLE", detail: "结果未知" },
          503,
        );
      }
      if (request.url.endsWith(`/quotations/${quotationId}`))
        return jsonResponse({
          ...quotation,
          current_version: refreshed
            ? {
                ...version,
                id: "00000000-0000-4000-8000-000000000399",
                version_number: 3,
                version: 1,
              }
            : version,
        });
      return jsonResponse({ items: [], count: 0 });
    });
    const view = renderWorkspace(quotationId);
    fireEvent.click(await screen.findByRole("button", { name: "提交审核" }));
    await screen.findByRole("button", { name: "原样重试上次报价操作" });
    expect(bodies[0]).toEqual({
      expected_version_id: versionId,
      expected_version: 7,
    });
    refreshed = true;
    await view.queryClient.invalidateQueries({ queryKey: ["quotation"] });
    await screen.findByText("QUOTE / V3");
    fireEvent.click(
      screen.getByRole("button", { name: "原样重试上次报价操作" }),
    );
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toEqual(bodies[0]);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
    await screen.findByRole("button", { name: "原样重试上次报价操作" });
    fireEvent.click(screen.getByRole("button", { name: "提交审核" }));
    await waitFor(() => expect(bodies).toHaveLength(3));
    expect(keys[2]).not.toBe(keys[1]);
    expect(bodies[2]).toEqual({
      expected_version_id: "00000000-0000-4000-8000-000000000399",
      expected_version: 1,
    });
  });

  it("retries inquiry creation with its original timestamp and key, rotating only edited input", async () => {
    window.localStorage.setItem(
      sessionKeys.organizationId,
      "00000000-0000-4000-8000-000000000001",
    );
    window.localStorage.setItem(sessionKeys.accessToken, "inquiry-writer");
    const bodies: unknown[] = [];
    const keys: (string | null)[] = [];
    let finish: (() => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input as Request;
      if (request.url.endsWith("/me/context"))
        return jsonResponse({ permissions: ["inquiry.write"] });
      if (request.method === "POST") {
        bodies.push(await request.json());
        keys.push(request.headers.get("Idempotency-Key"));
        await new Promise<void>((resolve) => {
          finish = resolve;
        });
        return bodies.length === 1
          ? jsonResponse(
              { status: 503, code: "UNAVAILABLE", detail: "结果未知" },
              503,
            )
          : jsonResponse({ id: quotation.inquiry_id }, 201);
      }
      return jsonResponse({ items: [], count: 0 });
    });
    renderWorkspace();
    fireEvent.click(
      await screen.findByRole("button", { name: "准备产品与询盘" }),
    );
    fireEvent.change(screen.getByLabelText("商机 ID *"), {
      target: { value: quotation.opportunity_id },
    });
    fireEvent.change(screen.getByLabelText("客户公司 ID *"), {
      target: { value: quotation.company_id },
    });
    fireEvent.change(screen.getByLabelText("客户参考号"), {
      target: { value: "RFQ-1" },
    });
    const description = screen.getByLabelText("询盘内容 *");
    fireEvent.change(description, {
      target: { value: "Confidential inquiry" },
    });
    const form = screen
      .getByRole("button", { name: "保存询盘" })
      .closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(description).toBeDisabled();
    expect(screen.getByRole("button", { name: "关闭" })).toBeDisabled();
    expect(bodies[0]).toMatchObject({
      received_at: expect.any(String),
      description: "Confidential inquiry",
    });
    finish?.();
    await waitFor(() => expect(description).not.toBeDisabled());
    expect(description).toHaveValue("Confidential inquiry");
    fireEvent.submit(form);
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toEqual(bodies[0]);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
    finish?.();
    await screen.findByText(`询盘已建立：${quotation.inquiry_id}`);
    await waitFor(() => expect(description).not.toBeDisabled());
    fireEvent.change(description, { target: { value: "Second inquiry" } });
    fireEvent.submit(form);
    await waitFor(() => expect(bodies).toHaveLength(3));
    expect(keys[2]).not.toBe(keys[1]);
    expect(bodies[2]).toMatchObject({ description: "Second inquiry" });
    finish?.();
    await waitFor(() => expect(description).not.toBeDisabled());
  });

  it("requires a scoped session before quotation data is requested", () => {
    renderWorkspace();
    expect(
      screen.getByRole("heading", { name: "连接你的业务空间" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("组织 ID")).toBeInTheDocument();
  });

  it("does not store an invalid connection", async () => {
    renderWorkspace();
    fireEvent.change(screen.getByLabelText("组织 ID"), {
      target: { value: "invalid" },
    });
    fireEvent.click(screen.getByRole("button", { name: "连接业务空间" }));
    expect(await screen.findByText("请输入有效的组织 ID")).toBeInTheDocument();
    expect(window.localStorage.getItem(sessionKeys.organizationId)).toBeNull();
    expect(window.localStorage.getItem(sessionKeys.accessToken)).toBeNull();
  });

  it("limits preparation to product writers and validates before creating exact cost defaults", async () => {
    window.localStorage.setItem(
      sessionKeys.organizationId,
      "00000000-0000-4000-8000-000000000001",
    );
    window.localStorage.setItem(sessionKeys.accessToken, "product-writer");
    const bodies: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input as Request;
      if (request.method === "POST") {
        bodies.push(await request.json());
        return jsonResponse({ id: "created-product" });
      }
      if (request.url.endsWith("/me/context"))
        return jsonResponse({ permissions: ["product.write", "profit.read"] });
      return jsonResponse({ items: [], count: 0 });
    });
    renderWorkspace();
    fireEvent.click(
      await screen.findByRole("button", { name: "准备产品与询盘" }),
    );
    expect(
      screen.queryByRole("heading", { name: "登记询盘" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存产品" }));
    await screen.findByText("请填写 SKU");
    expect(bodies).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("SKU *"), {
      target: { value: " PUMP-1 " },
    });
    fireEvent.change(screen.getByLabelText("产品名称 *"), {
      target: { value: "Pump" },
    });
    fireEvent.change(screen.getByLabelText("标准成本 *"), {
      target: { value: "123.4567" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存产品" }));
    await screen.findByText("产品已建立：created-product");
    expect(bodies).toEqual([
      {
        sku: "PUMP-1",
        name: "Pump",
        unit: "set",
        description: null,
        standard_cost: "123.4567",
        cost_currency: "CNY",
      },
    ]);
  });

  it.each([{ permissions: [] }, { permissions: ["quotation.read"] }])(
    "does not expose detail writes without command permissions %j",
    async ({ permissions }) => {
      window.localStorage.setItem(
        sessionKeys.organizationId,
        "00000000-0000-4000-8000-000000000001",
      );
      window.localStorage.setItem(sessionKeys.accessToken, "read-only-token");
      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const request = input instanceof Request ? input : new Request(input);
        if (request.url.endsWith("/me/context"))
          return jsonResponse({ permissions });
        if (request.url.endsWith(`/quotations/${quotationId}`))
          return jsonResponse(quotation);
        return jsonResponse({ items: [], count: 0 });
      });
      renderWorkspace(quotationId);
      expect(
        await screen.findByText("报价成本和毛利仅管理员、经理、财务可见。"),
      ).toBeInTheDocument();
      expect(screen.queryByText("36.36%")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "提交审核" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "生成修订版" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "标记过期" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "创建报价 V1" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "准备产品与询盘" }),
      ).not.toBeInTheDocument();
    },
  );

  it("renders the frozen margin snapshot and submits the current draft", async () => {
    window.localStorage.setItem(
      sessionKeys.organizationId,
      "00000000-0000-4000-8000-000000000001",
    );
    window.localStorage.setItem(
      sessionKeys.accessToken,
      "quotation-test-token",
    );
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input) => {
        const request = input instanceof Request ? input : new Request(input);
        if (request.url.endsWith("/me/context"))
          return jsonResponse({
            permissions: ["quotation.write", "quotation.submit", "profit.read"],
          });
        if (request.method === "POST") {
          return jsonResponse({ ...version, status: "INTERNAL_REVIEW" });
        }
        if (request.url.endsWith(`/api/v1/quotations/${quotationId}`)) {
          return jsonResponse(quotation);
        }
        return jsonResponse({
          items: [
            {
              id: quotationId,
              quotation_number: quotation.quotation_number,
              company_id: quotation.company_id,
              opportunity_id: quotation.opportunity_id,
              accepted_version_id: null,
              version_id: versionId,
              version_number: 2,
              status: "DRAFT",
              currency_code: "EUR",
              total: "110.0000",
              gross_profit: "40.0000",
              gross_margin: "0.3636",
              valid_until: "2026-10-04",
              created_at: quotation.created_at,
            },
          ],
          count: 1,
        });
      });

    renderWorkspace(quotationId);

    expect(
      await screen.findByRole("heading", { name: "Q-2026-000001" }),
    ).toBeInTheDocument();
    expect(screen.getByText("报价毛利")).toBeInTheDocument();
    expect(screen.getByText("36.36%")).toBeInTheDocument();
    expect(screen.getByText("316L sanitary pump")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "提交审核" }));

    await waitFor(() => {
      const submitRequest = fetchMock.mock.calls
        .map(([input]) => (input instanceof Request ? input : undefined))
        .find(
          (request) =>
            request?.method === "POST" && request.url.endsWith("/submit"),
        );
      expect(submitRequest).toBeDefined();
      expect(submitRequest?.headers.get("Authorization")).toBe(
        "Bearer quotation-test-token",
      );
    });
  });

  it("validates revision inputs and retains exact values after a failed submission", async () => {
    window.localStorage.setItem(
      sessionKeys.organizationId,
      "00000000-0000-4000-8000-000000000001",
    );
    window.localStorage.setItem(
      sessionKeys.accessToken,
      "quotation-test-token",
    );
    const bodies: unknown[] = [];
    const keys: (string | null)[] = [];
    let refreshed = false;
    let finish: (() => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      if (request.url.endsWith("/me/context"))
        return jsonResponse({ permissions: ["quotation.write"] });
      if (request.method === "POST") {
        bodies.push(await request.json());
        keys.push(request.headers.get("Idempotency-Key"));
        await new Promise<void>((resolve) => {
          finish = resolve;
        });
        return jsonResponse(
          { status: 503, code: "UNAVAILABLE", detail: "暂时不可用" },
          503,
        );
      }
      if (request.url.endsWith(`/quotations/${quotationId}`))
        return jsonResponse(
          refreshed
            ? {
                ...quotation,
                current_version: {
                  ...version,
                  id: "00000000-0000-4000-8000-000000000399",
                  version_number: 3,
                },
              }
            : quotation,
        );
      return jsonResponse({ items: [], count: 0 });
    });
    const view = renderWorkspace(quotationId);
    fireEvent.click(await screen.findByRole("button", { name: "生成修订版" }));
    const rate = screen.getByLabelText("基准汇率 *");
    const price = screen.getByLabelText("PUMP-CN 新单价");
    fireEvent.change(rate, { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "生成 V3" }));
    expect(await screen.findByText("汇率必须大于零")).toBeInTheDocument();
    expect(rate).toHaveFocus();
    expect(bodies).toHaveLength(0);
    fireEvent.change(rate, { target: { value: "1.12345678" } });
    fireEvent.change(price, { target: { value: "52.1234" } });
    fireEvent.click(screen.getByRole("button", { name: "生成 V3" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(rate).toBeDisabled();
    expect(price).toBeDisabled();
    expect(screen.getByRole("button", { name: "取消" })).toBeDisabled();
    expect(bodies[0]).toMatchObject({
      expected_version_id: versionId,
      exchange_rate: "1.12345678",
      valid_until: "2026-10-04",
      items: [
        {
          source_item_id: "00000000-0000-4000-8000-000000000303",
          quantity: "2.0000",
          unit_price: "52.1234",
        },
      ],
    });
    finish?.();
    await waitFor(() => expect(rate).not.toBeDisabled());
    expect(rate).toHaveValue("1.12345678");
    expect(price).toHaveValue("52.1234");
    expect(
      screen.getByRole("heading", { name: "生成 V3" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    refreshed = true;
    await view.queryClient.invalidateQueries({ queryKey: ["quotation"] });
    expect(
      screen.getByRole("heading", { name: "生成 V3" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "生成 V3" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
    expect(bodies[1]).toEqual(bodies[0]);
    finish?.();
    await waitFor(() => expect(rate).not.toBeDisabled());
    fireEvent.change(price, { target: { value: "53.0000" } });
    fireEvent.click(screen.getByRole("button", { name: "生成 V3" }));
    await waitFor(() => expect(bodies).toHaveLength(3));
    expect(keys[2]).not.toBe(keys[1]);
    expect(bodies[2]).toMatchObject({ expected_version_id: versionId });
    finish?.();
    await waitFor(() => expect(rate).not.toBeDisabled());
  });

  it("drops the open editor and cached quotation when the organization changes", async () => {
    const organizationA = "00000000-0000-4000-8000-000000000001";
    const organizationB = "00000000-0000-4000-8000-000000000002";
    window.localStorage.setItem(sessionKeys.organizationId, organizationA);
    window.localStorage.setItem(sessionKeys.accessToken, "organization-token");
    const detailScopes: (string | null)[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input as Request;
      if (request.url.endsWith("/me/context"))
        return jsonResponse({ permissions: ["quotation.write"] });
      if (request.url.endsWith(`/quotations/${quotationId}`)) {
        const organization = request.headers.get("X-Organization-ID");
        detailScopes.push(organization);
        return organization === organizationA
          ? jsonResponse(quotation)
          : jsonResponse({ status: 404 }, 404);
      }
      return jsonResponse({ items: [], count: 0 });
    });
    renderWorkspace(quotationId);
    fireEvent.click(await screen.findByRole("button", { name: "生成修订版" }));
    expect(
      screen.getByRole("heading", { name: "生成 V3" }),
    ).toBeInTheDocument();
    window.localStorage.setItem(sessionKeys.organizationId, organizationB);
    fireEvent(window, new Event("trade-workbench-session-change"));
    expect(
      await screen.findByRole("heading", { name: "无法读取报价" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "生成 V3" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("36.36%")).not.toBeInTheDocument();
    expect(detailScopes).toEqual([organizationA, organizationB]);
  });
});
