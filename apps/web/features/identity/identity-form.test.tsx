import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { IdentityForm, type IdentityEdit } from "./identity-form";
import { IdentityWorkspace } from "./identity-workspace";
import type { Member } from "./api";

function form(edit: IdentityEdit) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <IdentityForm
        scope="test"
        edit={edit}
        onDone={vi.fn()}
        onCancel={vi.fn()}
      />
    </QueryClientProvider>,
  );
}
beforeEach(() =>
  localStorage.setItem(
    "trade-workbench.organization-id",
    "00000000-0000-4000-8000-000000000001",
  ),
);
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});
it("requires verified subject, display name, reason and confirmation before granting access", async () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  form({ mode: "add" });
  fireEvent.click(screen.getByRole("button", { name: "确认添加成员" }));
  expect(
    await screen.findByText("请核对授权对象并确认影响"),
  ).toBeInTheDocument();
  expect(screen.getAllByText("请填写此项")).toHaveLength(2);
  expect(fetch).not.toHaveBeenCalled();
});
it("keeps opening membership version and key for unchanged retries", async () => {
  const requests: Request[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    requests.push((input as Request).clone());
    return new Response(
      JSON.stringify({
        type: "about:blank",
        title: "Unavailable",
        status: 503,
        code: "TEMPORARY",
        detail: "Retry",
        request_id: "test",
        errors: [],
      }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  });
  form({
    mode: "disable",
    member: {
      id: "00000000-0000-4000-8000-000000000003",
      version: 7,
      role: "VIEWER",
      display_name: "Verified",
      external_subject: "verified",
    } as Member,
  });
  fireEvent.change(screen.getByLabelText("组织管理操作原因"), {
    target: { value: "离职停用授权" },
  });
  fireEvent.click(
    screen.getByLabelText("我已核对授权对象、操作原因和权限影响"),
  );
  fireEvent.click(screen.getByRole("button", { name: "确认停用成员" }));
  await screen.findByText(
    "尚未确认请求结果。请先核对记录；未修改内容时重试不会重复授权。",
  );
  fireEvent.click(screen.getByRole("button", { name: "确认停用成员" }));
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests[0]!.headers.get("Idempotency-Key")).toBe(
    requests[1]!.headers.get("Idempotency-Key"),
  );
  expect(await requests[0]!.json()).toEqual({
    expected_version: 7,
    reason: "离职停用授权",
  });
});
it("does not fetch organization records or show commands to non-admin members", async () => {
  localStorage.setItem("trade-workbench.access-token", "test-token");
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ permissions: [] }), {
      headers: { "Content-Type": "application/json" },
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <IdentityWorkspace />
    </QueryClientProvider>,
  );
  expect(
    await screen.findByText("当前成员没有组织管理权限，请联系管理员。"),
  ).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(
    screen.queryByRole("button", { name: "添加已核实成员" }),
  ).not.toBeInTheDocument();
});
