import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthGate } from "./auth-gate";
import { sessionKeys } from "../features/leads/api";

const organization = "00000000-0000-4000-8000-000000000001";
const authenticated = {
  configured: true,
  authenticated: true,
  marker: "opaque-marker",
  organizations: {
    items: [{ organization_id: organization, name: "组织 A", role: "SALES" }],
  },
};
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
function respond(body: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok, json: async () => body }),
  );
}
function mount() {
  render(
    <AuthGate>
      <p>组织业务数据</p>
    </AuthGate>,
  );
}

it("hides business data until the server confirms authentication", async () => {
  localStorage.setItem(sessionKeys.accessToken, "old-browser-token");
  localStorage.setItem(sessionKeys.organizationId, organization);
  respond({ configured: true, authenticated: false });
  mount();
  expect(screen.queryByText("组织业务数据")).not.toBeInTheDocument();
  expect(await screen.findByRole("link", { name: "登录" })).toHaveAttribute(
    "href",
    "/api/auth/login",
  );
  expect(localStorage.getItem(sessionKeys.accessToken)).toBeNull();
});

it("offers only effective memberships and stores no authorization token", async () => {
  respond(authenticated);
  mount();
  const selector = await screen.findByLabelText("业务空间");
  fireEvent.change(selector, { target: { value: organization } });
  fireEvent.click(screen.getByRole("button", { name: "进入业务空间" }));
  expect(await screen.findByText("组织业务数据")).toBeInTheDocument();
  expect(localStorage.getItem(sessionKeys.accessToken)).toBeNull();
  expect(localStorage.getItem(sessionKeys.marker)).toBe("opaque-marker");
});

it("does not trust a stale foreign organization selection", async () => {
  localStorage.setItem(
    sessionKeys.organizationId,
    "00000000-0000-4000-8000-000000000002",
  );
  localStorage.setItem(sessionKeys.marker, "previous-user");
  respond(authenticated);
  mount();
  await screen.findByLabelText("业务空间");
  expect(screen.queryByText("组织业务数据")).not.toBeInTheDocument();
});

it("fails closed on service failure and clears old local credentials", async () => {
  localStorage.setItem(sessionKeys.accessToken, "old-token");
  localStorage.setItem(sessionKeys.marker, "old-marker");
  respond({}, false);
  mount();
  await screen.findByRole("alert");
  expect(screen.queryByText("组织业务数据")).not.toBeInTheDocument();
  expect(localStorage.getItem(sessionKeys.marker)).toBeNull();
  expect(localStorage.getItem(sessionKeys.accessToken)).toBeNull();
});

it("keeps the legacy fixture path only when the server explicitly enables it", async () => {
  respond({ configured: false, authenticated: false });
  mount();
  await screen.findByText("登录服务尚未配置");
  expect(screen.queryByText("组织业务数据")).not.toBeInTheDocument();
  respond({ configured: false, authenticated: false, test_bearer: true });
  fireEvent.click(screen.getByRole("button", { name: "重新检查" }));
  expect(await screen.findByText("组织业务数据")).toBeInTheDocument();
});

it("rechecks the session when returning to the browser", async () => {
  localStorage.setItem(sessionKeys.organizationId, organization);
  respond(authenticated);
  mount();
  await screen.findByText("组织业务数据");
  respond({ configured: true, authenticated: false });
  act(() => window.dispatchEvent(new Event("focus")));
  await waitFor(() =>
    expect(screen.queryByText("组织业务数据")).not.toBeInTheDocument(),
  );
  await screen.findByRole("link", { name: "登录" });
});

it("preserves unfinished input when a background check confirms the same session", async () => {
  localStorage.setItem(sessionKeys.organizationId, organization);
  respond(authenticated);
  render(
    <AuthGate>
      <input aria-label="未提交备注" defaultValue="" />
    </AuthGate>,
  );
  const input = await screen.findByLabelText("未提交备注");
  fireEvent.change(input, { target: { value: "尚未保存" } });
  act(() => window.dispatchEvent(new Event("focus")));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText("未提交备注")).toBe(input);
  expect(input).toHaveValue("尚未保存");
});
