import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CommercialTimeline } from "./commercial-timeline";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  scope: "session-a",
  permissions: ["quotation.read", "shipment.read", "order.read"],
}));
vi.mock("../overview/session", () => ({
  sessionClient: () => ({ GET: mocks.get }),
  useSessionScope: () => mocks.scope,
}));
vi.mock("../overview/api", () => ({
  useMemberContext: () => ({ data: { permissions: mocks.permissions } }),
}));
vi.mock("./work-review", () => ({ WorkTextReview: () => null }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  mocks.scope = "session-a";
  mocks.permissions = ["quotation.read", "shipment.read", "order.read"];
});
function result(text: string | null, hasMore = false) {
  return {
    data: {
      items: [
        {
          id: "activity-1",
          summary: text,
          details: {},
          content_visible: text !== null,
          occurred_at: "2026-09-08T00:00:00Z",
          activity_type: "quotation.created",
        },
      ],
      has_more: hasMore,
      next_cursor: hasMore ? "older-cursor" : null,
    },
  };
}
function setup(
  subject: "quotation" | "shipment" | "sales_order" = "quotation",
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
  });
  const view = (id = "owner-1", revision = 1) => (
    <QueryClientProvider client={client}>
      <CommercialTimeline subject={subject} id={id} revision={revision} />
    </QueryClientProvider>
  );
  return { ...render(view()), view, client };
}
it.each([
  ["quotation", "/api/v1/quotations/{quotation_id}/activities", "quotation_id"],
  ["shipment", "/api/v1/shipments/{shipment_id}/activities", "shipment_id"],
  [
    "sales_order",
    "/api/v1/sales-orders/{order_id}/activity-history",
    "order_id",
  ],
] as const)(
  "reads %s through the generated owner route",
  async (subject, route, key) => {
    mocks.get.mockResolvedValue(result(null));
    setup(subject);
    await screen.findByText("正文待审核，仅授权审核人可查看。");
    expect(mocks.get).toHaveBeenCalledWith(route, {
      params: {
        path: { [key]: "owner-1" },
        query: { cursor: undefined, limit: 20 },
      },
    });
  },
);
it("loads older pages and refreshes fresh first-page facts with the production cache timing", async () => {
  let firstReads = 0;
  mocks.get.mockImplementation(async (_route, options) => {
    if (options.params.query.cursor) return result("更早历史");
    firstReads += 1;
    return result(`最新历史${firstReads}`, true);
  });
  setup();
  await screen.findByText("最新历史1");
  fireEvent.click(screen.getByRole("button", { name: "下一页历史" }));
  await screen.findByText("更早历史");
  fireEvent.click(screen.getByRole("button", { name: "刷新时间线" }));
  await screen.findByText("最新历史2");
  expect(screen.queryByText("更早历史")).toBeNull();
  expect(screen.getByRole("button", { name: "上一页历史" })).toBeDisabled();
});
it("hides cached content on refresh failure and can retry", async () => {
  mocks.get.mockResolvedValue(result("敏感历史"));
  setup();
  await screen.findByText("敏感历史");
  mocks.get.mockRejectedValue(new Error("Forbidden"));
  fireEvent.click(screen.getByRole("button", { name: "刷新时间线" }));
  await screen.findByRole("alert");
  expect(screen.queryByText("敏感历史")).toBeNull();
  expect(screen.getByRole("button", { name: "下一页历史" })).toBeDisabled();
  mocks.get.mockResolvedValue(result(null));
  fireEvent.click(screen.getByRole("button", { name: "重试时间线" }));
  await screen.findByText("正文待审核，仅授权审核人可查看。");
});
it("never displays a late previous-session response", async () => {
  let finish!: (value: ReturnType<typeof result>) => void;
  mocks.get.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const ui = setup();
  await screen.findByText("正在读取历史记录…");
  expect(screen.getByRole("button", { name: "刷新时间线" })).toBeDisabled();
  mocks.scope = "session-b";
  mocks.get.mockResolvedValue(result("当前历史"));
  ui.rerender(ui.view());
  await screen.findByText("当前历史");
  await act(async () => {
    finish(result("前一账号历史"));
  });
  expect(screen.queryByText("前一账号历史")).toBeNull();
});
it("removes history when read permission is lost", async () => {
  mocks.get.mockResolvedValue(result("可见历史"));
  const ui = setup();
  await screen.findByText("可见历史");
  mocks.permissions = [];
  ui.rerender(ui.view());
  await screen.findByRole("alert");
  expect(screen.queryByText("可见历史")).toBeNull();
  expect(mocks.get).toHaveBeenCalledTimes(1);
});
it("refreshes after a new business revision and isolates another owner", async () => {
  mocks.get.mockResolvedValue(result("原记录"));
  const ui = setup();
  await screen.findByText("原记录");
  mocks.get.mockResolvedValue(result("新记录"));
  ui.rerender(ui.view("owner-1", 2));
  await screen.findByText("新记录");
  mocks.get.mockResolvedValue(result("另一对象"));
  ui.rerender(ui.view("owner-2", 2));
  await screen.findByText("另一对象");
  expect(screen.queryByText("新记录")).toBeNull();
});
