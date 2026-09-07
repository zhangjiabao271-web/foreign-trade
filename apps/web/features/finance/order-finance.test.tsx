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
import type { SalesOrder } from "../orders/api";
import { OrderFinance } from "./order-finance";

const member = vi.hoisted(() => ({ permissions: [] as string[] }));
vi.mock("../overview/api", () => ({
  useMemberContext: () => ({ data: { permissions: member.permissions } }),
}));

const order = {
  id: "00000000-0000-4000-8000-000000000401",
  company_id: "00000000-0000-4000-8000-000000000402",
  currency_code: "EUR",
  status: "EXECUTING",
  version: 3,
  deposit_due_date: "2026-09-05",
} as SalesOrder;

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OrderFinance order={order} />
    </QueryClientProvider>,
  );
}
function respond(body: object, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  member.permissions = [
    "receivable.write",
    "payment.record",
    "payment.allocate",
    "payment.reverse",
    "task.write",
    "order.complete",
  ];
  window.localStorage.setItem(
    sessionKeys.organizationId,
    "00000000-0000-4000-8000-000000000001",
  );
  window.localStorage.setItem(sessionKeys.accessToken, "finance-test-token");
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("order finance forms", () => {
  it.each([
    [],
    ["payment.record"],
    ["payment.allocate"],
    ["payment.reverse"],
    ["receivable.write"],
    ["task.write"],
    ["order.complete"],
  ])(
    "shows only explicitly granted command controls: %j",
    async (...granted) => {
      member.permissions = granted as string[];
      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const path = new URL((input as Request).url).pathname;
        if (path.endsWith("/payments"))
          return respond({
            items: [
              {
                id: "receipt",
                payment_number: "PAY-ROLE",
                kind: "RECEIPT",
                status: "ACTIVE",
                amount: "12.3400",
                available_amount: "12.3400",
                currency_code: "EUR",
                received_at: "2026-09-05T00:00:00Z",
                content_visible: false,
              },
            ],
            count: 1,
          });
        if (path.endsWith("/tasks"))
          return respond({
            items: [
              {
                id: "task",
                status: "OPEN",
                version: 1,
                content_visible: false,
                details: {},
              },
            ],
            count: 1,
          });
        return respond({ items: [], count: 0 });
      });
      renderPanel();
      await screen.findByText("PAY-ROLE");
      for (const [permission, name] of [
        ["receivable.write", "生成定金和尾款应收"],
        ["payment.record", "记录收款"],
        ["payment.allocate", "确认核销"],
        ["payment.reverse", "冲销 PAY-ROLE"],
        ["task.write", "完成此待办"],
        ["order.complete", "检查并完成订单"],
      ]) {
        expect(Boolean(screen.queryByRole("button", { name }))).toBe(
          member.permissions.includes(permission!),
        );
      }
      expect(
        screen.getByRole("button", { name: "查找收款" }),
      ).toBeInTheDocument();
      expect(
        screen.getByText("收款备注待审核，当前不可见"),
      ).toBeInTheDocument();
    },
  );
  it.each([false, true])(
    "uses server note visibility %s without hiding receipt identifiers",
    async (visible) => {
      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const url = new URL((input as Request).url);
        if (url.pathname.endsWith("/payments"))
          return respond({
            items: [
              {
                id: "00000000-0000-4000-8000-000000000901",
                payment_number: "PAY-REVIEW-001",
                reference: "BANK-IDENTIFIER",
                kind: "REVERSAL",
                status: "ACTIVE",
                amount: "12.3400",
                available_amount: "0.0000",
                currency_code: "EUR",
                received_at: "2026-09-05T00:00:00Z",
                content_visible: visible,
                notes: "本次汇款用途已核对",
                allocations: [],
              },
            ],
            count: 1,
          });
        return respond({ items: [], count: 0, permissions: [] });
      });
      renderPanel();
      await screen.findByText("PAY-REVIEW-001");
      expect(screen.getByText(/BANK-IDENTIFIER/)).toBeInTheDocument();
      expect(screen.getByText(/12.3400 EUR/)).toBeInTheDocument();
      if (visible)
        expect(screen.getByText("本次汇款用途已核对")).toBeInTheDocument();
      else {
        expect(
          screen.getByText("收款备注待审核，当前不可见"),
        ).toBeInTheDocument();
        expect(screen.queryByText("本次汇款用途已核对")).toBeNull();
      }
    },
  );
  it("scopes receipt pages to the customer and currency and resets the cursor on search", async () => {
    const cursor = "00000000-0000-4000-8000-000000000901";
    const calls: URL[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = new URL((input as Request).url);
      if (url.pathname.endsWith("/payments")) {
        calls.push(url);
        return respond({
          items: [],
          count: 0,
          has_more: !url.searchParams.has("cursor"),
          next_cursor: cursor,
        });
      }
      return respond({ items: [], count: 0 });
    });
    renderPanel();
    await screen.findByRole("heading", { name: "应收、回款与结案" });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "下一页收款" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "下一页收款" }));
    await waitFor(() =>
      expect(calls.at(-1)!.searchParams.get("cursor")).toBe(cursor),
    );
    expect(screen.getByText("第 2 页")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("查找当前客户收款"), {
      target: { value: "BANK-OLD" },
    });
    fireEvent.click(screen.getByRole("button", { name: "查找收款" }));
    await waitFor(() =>
      expect(calls.at(-1)!.searchParams.get("query")).toBe("BANK-OLD"),
    );
    expect(calls.at(-1)!.searchParams.has("cursor")).toBe(false);
    expect(screen.getByText("第 1 页")).toBeInTheDocument();
    for (const url of calls) {
      expect(url.searchParams.get("company_id")).toBe(order.company_id);
      expect(url.searchParams.get("currency_code")).toBe("EUR");
      expect(url.searchParams.get("limit")).toBe("20");
    }
  });

  it("shows a recoverable receipt query error without unmounting the recording form", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (new URL((input as Request).url).pathname.endsWith("/payments")) {
        return respond(
          {
            status: 503,
            code: "UNAVAILABLE",
            title: "Unavailable",
            detail: "收款查询暂不可用",
            type: "about:blank",
            request_id: "00000000-0000-4000-8000-000000000099",
            errors: [],
          },
          503,
        );
      }
      return respond({ items: [], count: 0 });
    });
    renderPanel();
    await screen.findByText("收款查询暂不可用");
    expect(
      screen.getByRole("button", { name: "重试收款查询" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("实收金额")).toBeInTheDocument();
    expect(screen.queryByText(/未找到收款/)).not.toBeInTheDocument();
  });

  it("rejects zero and excessive decimal precision before recording", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => respond({ items: [], count: 0 }));
    renderPanel();
    await screen.findByRole("heading", { name: "应收、回款与结案" });
    fireEvent.change(screen.getByLabelText("实收金额"), {
      target: { value: "0.0000" },
    });
    fireEvent.change(screen.getByLabelText("收款日期"), {
      target: { value: "2026-09-05" },
    });
    fireEvent.click(screen.getByRole("button", { name: "记录收款" }));
    expect(await screen.findByText("金额必须大于零")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("实收金额"), {
      target: { value: "1.00001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "记录收款" }));
    expect(await screen.findByText("金额最多保留四位小数")).toBeInTheDocument();
    expect(
      fetch.mock.calls.filter(
        ([input]) => input instanceof Request && input.method === "POST",
      ),
    ).toHaveLength(0);
  });

  it("keeps the command key on a failed retry and preserves decimal strings", async () => {
    const posts: Request[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input as Request;
      if (request.method === "POST") {
        posts.push(request.clone());
        return respond(
          {
            code: "TEMPORARY_FAILURE",
            title: "Unavailable",
            status: 503,
            detail: "请重试",
            request_id: "00000000-0000-4000-8000-000000000099",
            errors: [],
            type: "about:blank",
          },
          503,
        );
      }
      return respond({ items: [], count: 0 });
    });
    renderPanel();
    await screen.findByRole("heading", { name: "应收、回款与结案" });
    fireEvent.change(screen.getByLabelText("实收金额"), {
      target: { value: "12.3400" },
    });
    fireEvent.change(screen.getByLabelText("收款日期"), {
      target: { value: "2026-09-05" },
    });
    fireEvent.click(screen.getByRole("button", { name: "记录收款" }));
    await screen.findByText("请重试");
    fireEvent.click(screen.getByRole("button", { name: "记录收款" }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[0]!.headers.get("Idempotency-Key")).toBeTruthy();
    expect(posts[0]!.headers.get("Idempotency-Key")).toBe(
      posts[1]!.headers.get("Idempotency-Key"),
    );
    expect(posts[0]!.headers.get("Authorization")).toBe(
      "Bearer finance-test-token",
    );
    expect((await posts[0]!.json()).amount).toBe("12.3400");
  });

  it("explains forbidden reads and offers a retry", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      respond(
        {
          status: 403,
          code: "PERMISSION_DENIED",
          title: "Forbidden",
          detail: "Permission required",
          type: "about:blank",
        },
        403,
      ),
    );
    renderPanel();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "当前成员没有此操作权限",
    );
    expect(
      screen.getByRole("button", { name: "重试财务数据" }),
    ).toBeInTheDocument();
  });
});
