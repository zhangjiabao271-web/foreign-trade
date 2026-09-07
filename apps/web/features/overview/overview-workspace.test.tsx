import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { OverviewWorkspace } from "./overview-workspace";
import { connectSession } from "./session";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});
function response(body: object) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
}
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <OverviewWorkspace />
    </QueryClientProvider>,
  );
  return client;
}

it("validates connection without sending invalid credentials", async () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  mount();
  fireEvent.click(screen.getByRole("button", { name: "连接业务空间" }));
  expect(await screen.findByText("请输入有效的组织 ID")).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalled();
});

it("shows real queue rows, next page, and prevents cross-session cache reuse", async () => {
  connectSession("00000000-0000-4000-8000-000000000001", "first-token");
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const request = input as Request;
    const url = new URL(request.url);
    if (url.pathname.endsWith("/me/context"))
      return response({ permissions: ["overview.read", "lead.read"] });
    const secondSession =
      request.headers.get("Authorization") === "Bearer second-token";
    const secondPage = url.searchParams.get("offset") === "5";
    return response({
      queue: "leads",
      business_date: "2026-09-06",
      has_more: !secondPage,
      next_offset: secondPage ? null : 5,
      items: [
        {
          id: "lead-1",
          title: secondSession
            ? "组织 B 客户"
            : secondPage
              ? "下一页客户"
              : "组织 A 客户",
          href: "/leads/lead-1",
          status: "NEW",
          due_date: null,
          overdue: false,
          next_action: "跟进客户",
          missing_document_types: [],
        },
      ],
    });
  });
  const client = mount();
  expect(await screen.findByText("组织 A 客户")).toBeInTheDocument();
  const queue = screen.getByRole("region", { name: "待跟进线索" });
  fireEvent.click(within(queue).getByRole("button", { name: "下一页" }));
  expect(await screen.findByText("下一页客户")).toBeInTheDocument();
  act(() =>
    connectSession("00000000-0000-4000-8000-000000000002", "second-token"),
  );
  expect(screen.queryByText("下一页客户")).not.toBeInTheDocument();
  expect(await screen.findByText("组织 B 客户")).toBeInTheDocument();
  const keys = JSON.stringify(
    client
      .getQueryCache()
      .getAll()
      .map((query) => query.queryKey),
  );
  expect(keys).not.toContain("first-token");
  expect(keys).not.toContain("second-token");
});
