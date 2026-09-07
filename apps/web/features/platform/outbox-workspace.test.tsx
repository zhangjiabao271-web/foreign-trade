import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { OutboxWorkspace } from "./outbox-workspace";
import { connectSession } from "../overview/session";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});
function response(body: object, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function mount() {
  connectSession("00000000-0000-4000-8000-000000000001", "fixture-token");
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <OutboxWorkspace />
    </QueryClientProvider>,
  );
}
const event = {
  id: "00000000-0000-4000-8000-000000000002",
  event_type: "fixture.failed.v1",
  aggregate_type: "fixture",
  aggregate_id: "fixture-id",
  correlation_id: "trace-id",
  last_error: "CONSUMER_RECEIPT_TIMEOUT",
  attempt_count: 5,
  version: 7,
  created_at: "2026-09-06T08:00:00Z",
};
it("does not fetch events without read permission", async () => {
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(response({ permissions: [] }));
  mount();
  expect(
    await screen.findByText("当前成员没有失败事件查看权限。"),
  ).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(1);
});
it("requires reason and confirmation, sends version and reports requeue only", async () => {
  let posted: object | undefined;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const request = input as Request;
    if (request.url.endsWith("/me/context"))
      return response({ permissions: ["outbox.read", "outbox.replay"] });
    if (request.method === "POST") {
      posted = await request.json();
      return response({ ...event, status: "PENDING" });
    }
    return response({
      items: posted ? [] : [event],
      has_more: false,
      next_offset: null,
    });
  });
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "准备重放" }));
  fireEvent.click(screen.getByRole("button", { name: "确认重新排队" }));
  expect(await screen.findByText("请填写重放原因")).toBeInTheDocument();
  expect(posted).toBeUndefined();
  fireEvent.change(screen.getByLabelText("重放原因"), {
    target: { value: "  依赖服务已恢复  " },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "确认重新排队" }));
  expect(
    await screen.findByText(
      "事件已重新排队，尚不代表处理完成。请在相关业务对象核对结果。",
    ),
  ).toBeInTheDocument();
  expect(posted).toEqual({ reason: "依赖服务已恢复", expected_version: 7 });
  await waitFor(() =>
    expect(screen.queryByText("fixture.failed.v1")).not.toBeInTheDocument(),
  );
});
it("supports read-only pagination", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const request = input as Request;
    if (request.url.endsWith("/me/context"))
      return response({ permissions: ["outbox.read"] });
    if (request.url.includes("offset=10"))
      return response({ items: [], has_more: false });
    return response({ items: [event], has_more: true, next_offset: 10 });
  });
  mount();
  expect(
    await screen.findByText("当前成员只能查看，无重放权限。"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "准备重放" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(await screen.findByText(/当前页没有失败事件/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
});

it("keeps the reason on conflict and permits cancel then refresh", async () => {
  let postCount = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const request = input as Request;
    if (request.url.endsWith("/me/context"))
      return response({ permissions: ["outbox.read", "outbox.replay"] });
    if (request.method === "POST") {
      postCount += 1;
      return response(
        {
          status: 409,
          code: "VERSION_CONFLICT",
          title: "Conflict",
          detail: "Refresh",
          request_id: "fixture",
        },
        409,
      );
    }
    return response({ items: [event], has_more: false });
  });
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "准备重放" }));
  fireEvent.change(screen.getByLabelText("重放原因"), {
    target: { value: "保留核对记录" },
  });
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "确认重新排队" }));
  expect(
    await screen.findByText(
      "事件状态已变化。请刷新列表后重新核对，不要重复提交。",
    ),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("重放原因")).toHaveValue("保留核对记录");
  expect(postCount).toBe(1);
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(screen.getByRole("button", { name: "刷新列表" })).toBeEnabled();
});
