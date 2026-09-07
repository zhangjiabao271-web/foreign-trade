import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CreateQuotePanel } from "./create-quote-panel";
import { quotationCreateSchema } from "./create-schema";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
describe("quotation creation", () => {
  it("reuses unchanged retries, rotates edited requests and guards synchronous double submit", async () => {
    const keys: (string | null)[] = [];
    const bodies: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input as Request;
      keys.push(request.headers.get("Idempotency-Key"));
      bodies.push(await request.json());
      if (keys.length < 3) throw new TypeError("Response lost");
      return new Response(JSON.stringify({ id: "recovered-quote" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      });
    });
    const onCreated = vi.fn();
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { mutations: { retry: false } } })
        }
      >
        <CreateQuotePanel onClose={vi.fn()} onCreated={onCreated} />
      </QueryClientProvider>,
    );
    const id = "00000000-0000-4000-8000-000000000001";
    for (const label of ["询盘 ID *", "产品 ID *"]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: id } });
    }
    fireEvent.change(screen.getByLabelText("有效期 *"), {
      target: { value: "2026-10-04" },
    });
    const submit = screen.getByRole("button", { name: "创建报价 V1" });
    fireEvent.submit(submit.closest("form")!);
    fireEvent.submit(submit.closest("form")!);
    await screen.findByText(
      "创建结果未确认。保持输入不变再次提交可找回原报价。",
    );
    expect(keys).toHaveLength(1);
    fireEvent.click(submit);
    await waitFor(() => expect(keys).toHaveLength(2));
    await screen.findByText(
      "创建结果未确认。保持输入不变再次提交可找回原报价。",
    );
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
    expect(bodies[1]).toEqual(bodies[0]);
    fireEvent.change(screen.getByLabelText("销售单价 *"), {
      target: { value: "20.1234" },
    });
    fireEvent.click(submit);
    await waitFor(() =>
      expect(onCreated).toHaveBeenCalledWith("recovered-quote"),
    );
    expect(keys).toHaveLength(3);
    expect(keys[2]).not.toBe(keys[1]);
    expect(bodies[2]).toMatchObject({ items: [{ unit_price: "20.1234" }] });
  });
  it("validates before POST and preserves exact defaults and selected lines after failure", async () => {
    const bodies: unknown[] = [];
    let finish: (() => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input as Request;
      bodies.push(await request.json());
      await new Promise<void>((resolve) => {
        finish = resolve;
      });
      return new Response(
        JSON.stringify({
          status: 503,
          title: "Unavailable",
          type: "about:blank",
          request_id: "test-request",
          errors: [],
          code: "UNAVAILABLE",
          detail: "服务暂时不可用",
        }),
        { status: 503, headers: { "content-type": "application/json" } },
      );
    });
    const onCreated = vi.fn();
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { mutations: { retry: false } } })
        }
      >
        <CreateQuotePanel onClose={vi.fn()} onCreated={onCreated} />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "创建报价 V1" }));
    expect(await screen.findByText("请输入有效的询盘 ID")).toBeInTheDocument();
    expect(screen.getByLabelText("询盘 ID *")).toHaveFocus();
    expect(bodies).toHaveLength(0);
    const id = "00000000-0000-4000-8000-000000000001";
    fireEvent.change(screen.getByLabelText("询盘 ID *"), {
      target: { value: id },
    });
    fireEvent.change(screen.getByLabelText("产品 ID *"), {
      target: { value: id },
    });
    fireEvent.change(screen.getByLabelText("有效期 *"), {
      target: { value: "2026-10-04" },
    });
    fireEvent.change(screen.getByLabelText("销售单价 *"), {
      target: { value: "12.3456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加一行" }));
    fireEvent.click(screen.getAllByRole("button", { name: "移除此行" })[1]);
    fireEvent.click(screen.getByRole("button", { name: "创建报价 V1" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(screen.getByLabelText("询盘 ID *")).toBeDisabled();
    expect(screen.getByRole("button", { name: "取消" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "添加一行" })).toBeDisabled();
    expect(bodies[0]).toMatchObject({
      inquiry_id: id,
      exchange_rate: "7.10000000",
      items: [
        {
          product_id: id,
          quantity: "1.0000",
          unit_price: "12.3456",
        },
      ],
    });
    expect((bodies[0] as { items: unknown[] }).items).toHaveLength(1);
    for (const field of [
      "unit_cost",
      "cost_currency",
      "cost_exchange_rate",
      "allocated_cost",
    ]) {
      expect((bodies[0] as { items: unknown[] }).items[0]).not.toHaveProperty(
        field,
      );
    }
    expect(screen.queryByLabelText("成本单价")).not.toBeInTheDocument();
    finish?.();
    await screen.findByText(/UNAVAILABLE/);
    expect(screen.getByLabelText("销售单价 *")).toHaveValue("12.3456");
    expect(onCreated).not.toHaveBeenCalled();
  });
  it("rejects invalid precision, zero quantity and malformed currency", () => {
    const base = {
      inquiryId: "00000000-0000-4000-8000-000000000001",
      currency: "EUR",
      baseCurrency: "USD",
      exchangeRate: "1.08000000",
      validUntil: "2026-10-04",
      paymentTerms: "",
      deliveryTerms: "",
      items: [
        {
          product_id: "00000000-0000-4000-8000-000000000001",
          quantity: "1.0000",
          unit_price: "0.0000",
          unit_cost: "",
          cost_currency: "",
          cost_exchange_rate: "1.00000000",
          tax_amount: "0",
          freight_amount: "0",
          allocated_cost: "0",
        },
      ],
    };
    expect(quotationCreateSchema.parse(base)).toEqual(base);
    for (const changes of [
      { quantity: "0" },
      { unit_price: "1.23456" },
      { unit_cost: "-1" },
      { cost_currency: "EURO" },
      { cost_exchange_rate: "0" },
    ]) {
      expect(
        quotationCreateSchema.safeParse({
          ...base,
          items: [{ ...base.items[0], ...changes }],
        }).success,
      ).toBe(false);
    }
  });
});
