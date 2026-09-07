import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { sessionKeys } from "./api";
import { LeadWorkspace } from "./lead-workspace";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

function renderWorkspace(initialLeadId?: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <LeadWorkspace initialLeadId={initialLeadId} />
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("LeadWorkspace", () => {
  beforeEach(() => {
    window.localStorage.clear();
    push.mockReset();
    vi.restoreAllMocks();
  });

  afterEach(() => cleanup());

  it("requires a browser-scoped business session before loading tenant data", () => {
    renderWorkspace();

    expect(
      screen.getByRole("heading", { name: "连接你的业务空间" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("组织 ID")).toBeInTheDocument();
    expect(screen.getByLabelText("访问令牌")).toBeInTheDocument();
  });

  it("shows the empty state and creates a lead through the generated client", async () => {
    window.localStorage.setItem(
      sessionKeys.organizationId,
      "00000000-0000-4000-8000-000000000001",
    );
    window.localStorage.setItem(
      sessionKeys.accessToken,
      "test-access-token-value",
    );
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input, init) => {
        const url = input instanceof Request ? input.url : String(input);
        if (url.endsWith("/api/v1/me/context")) {
          return jsonResponse({ permissions: ["lead.read", "lead.write"] });
        }
        const method = input instanceof Request ? input.method : init?.method;
        if (method === "POST") {
          return jsonResponse(
            {
              id: "00000000-0000-4000-8000-000000000101",
              company_name: "Northwind Marine",
              contact_name: null,
              email: null,
              phone: null,
              country_code: null,
              source: null,
              notes: null,
              status: "NEW",
              converted_company_id: null,
              converted_contact_id: null,
              converted_opportunity_id: null,
              converted_at: null,
              version: 1,
              created_at: "2026-09-03T12:00:00Z",
            },
            201,
          );
        }
        return jsonResponse({ items: [], count: 0 });
      });

    renderWorkspace();
    expect(await screen.findByText("暂无匹配线索")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "登记新线索" })[0]!);
    fireEvent.change(screen.getByLabelText("公司名称 *"), {
      target: { value: "Northwind Marine" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登记线索" }));

    await waitFor(() =>
      expect(push).toHaveBeenCalledWith(
        "/leads/00000000-0000-4000-8000-000000000101",
      ),
    );
    expect(fetchMock).toHaveBeenCalled();
    const request = fetchMock.mock.calls
      .map(([input]) => (input instanceof Request ? input : undefined))
      .find((candidate) => candidate?.method === "POST");
    expect(request?.headers.get("Authorization")).toBe(
      "Bearer test-access-token-value",
    );
    expect(request?.headers.get("X-Organization-ID")).toBe(
      "00000000-0000-4000-8000-000000000001",
    );
  });

  it.each(["NEW", "RESPONDED"])(
    "keeps %s lead details readable without creation, transition or conversion controls",
    async (status) => {
      localStorage.setItem(
        sessionKeys.organizationId,
        "00000000-0000-4000-8000-000000000001",
      );
      localStorage.setItem(sessionKeys.marker, "real-session-marker");
      vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
        const url = input instanceof Request ? input.url : String(input);
        if (url.endsWith("/me/context"))
          return jsonResponse({ permissions: ["lead.read"] });
        if (url.endsWith("/leads/lead-id"))
          return jsonResponse({
            id: "lead-id",
            company_name: "只读测试线索",
            status,
            version: 1,
            content_visible: false,
            activities: [],
          });
        return jsonResponse({ items: [], count: 0 });
      });
      renderWorkspace("lead-id");
      expect(
        await screen.findByRole("heading", { name: "只读测试线索" }),
      ).toBeInTheDocument();
      expect(screen.getByText("当前权限不允许修改线索。")).toBeInTheDocument();
      for (const name of [
        "登记新线索",
        "确认有效",
        "排除线索",
        "转换为客户与商机",
        "审核文本开放范围",
      ]) {
        expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
      }
    },
  );

  it("fails closed while permission lookup is pending or fails", async () => {
    localStorage.setItem(
      sessionKeys.organizationId,
      "00000000-0000-4000-8000-000000000001",
    );
    localStorage.setItem(sessionKeys.marker, "real-session-marker");
    let finish!: (value: Response) => void;
    const permissionResponse = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = input instanceof Request ? input.url : String(input);
      return url.endsWith("/me/context")
        ? permissionResponse
        : jsonResponse({ items: [], count: 0 });
    });
    renderWorkspace();
    expect(
      await screen.findByText("正在确认线索操作权限…"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "登记新线索" }),
    ).not.toBeInTheDocument();
    finish(
      jsonResponse({ detail: "denied", code: "FORBIDDEN", status: 403 }, 403),
    );
    expect(
      await screen.findByText("无法确认线索操作权限，请刷新后重试。"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "登记新线索" }),
    ).not.toBeInTheDocument();
  });

  it("requires the separate conversion permission for a responded lead", async () => {
    localStorage.setItem(
      sessionKeys.organizationId,
      "00000000-0000-4000-8000-000000000001",
    );
    localStorage.setItem(sessionKeys.marker, "writer-session");
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.endsWith("/me/context"))
        return jsonResponse({ permissions: ["lead.read", "lead.write"] });
      if (url.endsWith("/leads/lead-id"))
        return jsonResponse({
          id: "lead-id",
          company_name: "独立转换权限",
          status: "RESPONDED",
          version: 1,
          content_visible: false,
          activities: [],
        });
      return jsonResponse({ items: [], count: 0 });
    });
    renderWorkspace("lead-id");
    expect(
      await screen.findByRole("heading", { name: "独立转换权限" }),
    ).toBeInTheDocument();
    expect(
      (await screen.findAllByRole("button", { name: "登记新线索" })).length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: "转换为客户与商机" }),
    ).not.toBeInTheDocument();
  });

  it("removes an open creation form when the session loses write permission", async () => {
    localStorage.setItem(
      sessionKeys.organizationId,
      "00000000-0000-4000-8000-000000000001",
    );
    localStorage.setItem(sessionKeys.marker, "manager-session");
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.endsWith("/me/context"))
        return jsonResponse({
          permissions:
            localStorage.getItem(sessionKeys.marker) === "manager-session"
              ? ["lead.read", "lead.write"]
              : ["lead.read"],
        });
      return jsonResponse({ items: [], count: 0 });
    });
    renderWorkspace();
    fireEvent.click(
      (await screen.findAllByRole("button", { name: "登记新线索" }))[0]!,
    );
    expect(
      screen.getByRole("heading", { name: "登记潜在客户" }),
    ).toBeInTheDocument();
    localStorage.setItem(sessionKeys.marker, "viewer-session");
    fireEvent(window, new Event("trade-workbench-session-change"));
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "登记潜在客户" }),
      ).not.toBeInTheDocument(),
    );
    expect(
      screen.queryByRole("button", { name: "登记新线索" }),
    ).not.toBeInTheDocument();
  });
});
