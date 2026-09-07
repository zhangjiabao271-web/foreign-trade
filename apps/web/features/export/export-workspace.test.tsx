import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ExportWorkspace } from "./export-workspace";
import { connectSession } from "../overview/session";
import { refundDifference } from "./amounts";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

it("preserves four-place refund differences without floating point", () => {
  expect(refundDifference("12.3400", "12.0000")).toBe("0.3400");
  expect(refundDifference("99999999999999.9999", "0.0001")).toBe(
    "99999999999999.9998",
  );
});
afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});
function respond(body: object) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
}
function mount(id?: string) {
  connectSession("00000000-0000-4000-8000-000000000001", "export-test-token");
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ExportWorkspace kind="customs" id={id} />
    </QueryClientProvider>,
  );
}

it("hides write controls for a read-only member", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = new URL((input as Request).url);
    if (url.pathname.endsWith("/me/context"))
      return respond({ permissions: ["export.read"] });
    if (url.pathname.endsWith("/activities"))
      return respond({ items: [], has_more: false, next_cursor: null });
    return respond({
      id: "case-1",
      declaration_number: "CUS-READ-001",
      shipment_id: "shipment-1",
      status: "DRAFT",
      declared_amount: "12.3400",
      currency_code: "USD",
      version: 1,
      missing_document_types: ["COMMERCIAL_INVOICE"],
      follow_up_date: null,
      submitted_on: null,
      external_reference: null,
    });
  });
  mount("case-1");
  expect(
    await screen.findByRole("heading", { name: "CUS-READ-001" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "开始准备资料" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "保存跟进安排" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("人工申报金额：12.3400 USD")).toBeInTheDocument();
});

it("rejects an invalid creation amount without posting", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input) => {
      if ((input as Request).url.endsWith("/me/context"))
        return respond({ permissions: ["export.read", "export.write"] });
      return respond({ items: [], has_more: false, next_cursor: null });
    });
  mount();
  await screen.findByText("新建报关案件");
  fireEvent.click(screen.getByText("新建报关案件"));
  fireEvent.change(screen.getByLabelText("出货 ID"), {
    target: { value: "00000000-0000-4000-8000-000000000009" },
  });
  fireEvent.change(screen.getByLabelText("人工申报金额"), {
    target: { value: "0.0000" },
  });
  fireEvent.click(screen.getByRole("button", { name: "创建人工跟踪案件" }));
  expect(await screen.findByText("金额必须大于零")).toBeInTheDocument();
  expect(
    fetch.mock.calls.filter(([input]) => (input as Request).method === "POST"),
  ).toHaveLength(0);
});
