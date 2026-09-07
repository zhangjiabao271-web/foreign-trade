import { renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useUploadRetry } from "./use-upload-retry";

const session = vi.hoisted(() => ({ scope: "organization-a:session-1" }));
vi.mock("../overview/session", () => ({
  useSessionScope: () => session.scope,
}));

it("retains retry identity through rerenders and isolates changed sessions", () => {
  const hook = renderHook(() => useUploadRetry());
  const first = hook.result.current();
  first.attempt = { fingerprint: "original", key: "first-key" };
  hook.rerender();
  expect(hook.result.current()).toBe(first);
  session.scope = "organization-b:session-2";
  hook.rerender();
  const second = hook.result.current();
  expect(second).not.toBe(first);
  expect(second.attempt).toBeUndefined();
  // A finishing old request only clears its captured old-session holder.
  first.attempt = undefined;
  second.attempt = { fingerprint: "new", key: "second-key" };
  expect(hook.result.current().attempt?.key).toBe("second-key");
});
