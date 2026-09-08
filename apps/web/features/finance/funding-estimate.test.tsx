import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FundingEstimate } from "./funding-estimate";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../overview/session", () => ({
  sessionClient: () => ({ GET: mocks.get }),
}));
const permissions = [
  "order.read",
  "expense.read",
  "receivable.read",
  "profit.read",
];
const data = {
  sales_order_id: "order-1",
  currency_code: "CNY",
  quoted_total_cost: "734.1000",
  net_additional_cost: "12.3456",
  net_allocated_receipts: "375.0000",
  estimated_funding_need: "371.4456",
};
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

function setup(allowed = permissions) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = (rights: string[]) => (
    <QueryClientProvider client={client}>
      <FundingEstimate
        scope="org-a:sales-session"
        orderId="order-1"
        permissions={rights}
      />
    </QueryClientProvider>
  );
  return { ...render(view(allowed)), view, client };
}

it.each(permissions)(
  "does not fetch or display estimate without %s",
  (missing) => {
    setup(permissions.filter((p) => p !== missing));
    expect(mocks.get).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: "垫资估算" })).toBeNull();
  },
);

it("displays exact server decimals, inputs and limitations; hides them on loss of access", async () => {
  mocks.get.mockResolvedValue({ data });
  const ui = setup();
  await screen.findByText("371.4456 CNY");
  expect(screen.getByText(/报价成本：734.1000 CNY/)).toBeInTheDocument();
  expect(screen.getByText(/非实际现金缺口/)).toBeInTheDocument();
  expect(screen.getByText(/估算为零也不保证无需准备资金/)).toBeInTheDocument();
  ui.rerender(ui.view([]));
  expect(screen.queryByText("371.4456 CNY")).toBeNull();
});

it("shows pending and retry states without inventing a zero value", async () => {
  let reject!: (error: Error) => void;
  mocks.get.mockReturnValue(
    new Promise((_, failure) => {
      reject = failure;
    }),
  );
  setup();
  await screen.findByText("正在更新垫资估算…");
  expect(screen.getByRole("button", { name: "刷新垫资估算" })).toBeDisabled();
  expect(screen.queryByText("0.0000 CNY")).toBeNull();
  reject(new Error("Unavailable"));
  await screen.findByRole("alert");
  mocks.get.mockResolvedValue({
    data: { ...data, estimated_funding_need: "0.0000" },
  });
  fireEvent.click(screen.getByRole("button", { name: "重试垫资估算" }));
  await screen.findByText("0.0000 CNY");
});

it("isolates a late response after switching order and session", async () => {
  let finish!: (value: { data: typeof data }) => void;
  mocks.get.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const ui = setup();
  mocks.get.mockResolvedValue({
    data: { ...data, estimated_funding_need: "8.0000" },
  });
  ui.rerender(
    <QueryClientProvider client={ui.client}>
      <FundingEstimate
        scope="org-b:new-session"
        orderId="order-2"
        permissions={permissions}
      />
    </QueryClientProvider>,
  );
  await screen.findByText("8.0000 CNY");
  await act(async () => {
    finish({ data });
  });
  expect(screen.queryByText("371.4456 CNY")).toBeNull();
  expect(screen.getByText("8.0000 CNY")).toBeInTheDocument();
});

it("removes cached numbers when a refresh loses authorization", async () => {
  mocks.get.mockResolvedValue({ data });
  setup();
  await screen.findByText("371.4456 CNY");
  mocks.get.mockRejectedValue(new Error("Forbidden"));
  fireEvent.click(screen.getByRole("button", { name: "刷新垫资估算" }));
  await screen.findByRole("alert");
  expect(screen.queryByText("371.4456 CNY")).toBeNull();
});
