import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { logtoConfig, sameOriginWrite, testBearerEnabled } from "./config";

beforeEach(() => {
  vi.stubEnv("LOGTO_ENDPOINT", "https://identity.example.test");
  vi.stubEnv("APP_BASE_URL", "https://trade.example.test");
  vi.stubEnv("LOGTO_APP_ID", "fixture-app");
  vi.stubEnv("LOGTO_APP_SECRET", "fixture-secret");
  vi.stubEnv(
    "LOGTO_COOKIE_SECRET",
    "fixture-cookie-secret-at-least-32-characters",
  );
  vi.stubEnv("LOCAL_AUTH_ALLOW_HTTP", "false");
  vi.stubEnv("E2E_AUTH_MODE", "");
});
afterEach(() => vi.unstubAllEnvs());

describe("server-side authentication configuration", () => {
  it("requires all session settings and secure production cookies", () => {
    expect(logtoConfig()?.cookieSecure).toBe(true);
    vi.stubEnv("LOGTO_APP_SECRET", "");
    expect(logtoConfig()).toBeNull();
  });

  it.each([
    "http://identity.example.test",
    "https://user:password@identity.example.test",
    "https://identity.example.test?secret=value",
    "https://identity.example.test#fragment",
    "javascript:alert(1)",
  ])("rejects unsafe endpoint %s", (endpoint) => {
    vi.stubEnv("LOGTO_ENDPOINT", endpoint);
    expect(() => logtoConfig()).toThrow();
  });

  it("permits HTTP only for explicitly enabled loopback development", () => {
    vi.stubEnv("LOGTO_ENDPOINT", "http://logto.localhost:3001");
    vi.stubEnv("APP_BASE_URL", "http://localhost:3000");
    expect(() => logtoConfig()).toThrow();
    vi.stubEnv("LOCAL_AUTH_ALLOW_HTTP", "true");
    expect(logtoConfig()?.cookieSecure).toBe(false);
    vi.stubEnv("LOGTO_ENDPOINT", "http://identity.example.test");
    expect(() => logtoConfig()).toThrow();
  });

  it("rejects weak encryption secrets and callback base paths", () => {
    vi.stubEnv("LOGTO_COOKIE_SECRET", "short");
    expect(() => logtoConfig()).toThrow();
    vi.stubEnv(
      "LOGTO_COOKIE_SECRET",
      "fixture-cookie-secret-at-least-32-characters",
    );
    vi.stubEnv("APP_BASE_URL", "https://trade.example.test/other");
    expect(() => logtoConfig()).toThrow();
  });

  it("never permits fixture bearer credentials in production", () => {
    vi.stubEnv("NODE_ENV", "test");
    expect(testBearerEnabled()).toBe(false);
    vi.stubEnv("E2E_AUTH_MODE", "bearer");
    expect(testBearerEnabled()).toBe(true);
    vi.stubEnv("NODE_ENV", "production");
    expect(testBearerEnabled()).toBe(false);
  });
});

describe("cookie-authenticated writes", () => {
  const base = "https://trade.example.test";
  it.each<Record<string, string>>([
    {},
    { origin: "null" },
    { origin: "https://attacker.example.test" },
    { origin: base, "sec-fetch-site": "cross-site" },
  ])("rejects missing or cross-site origin %#", (headers) => {
    expect(
      sameOriginWrite(new Request(base, { method: "POST", headers }), base),
    ).toBe(false);
  });
  it("allows matching origin writes and safe reads", () => {
    expect(
      sameOriginWrite(
        new Request(base, {
          method: "POST",
          headers: { origin: base, "sec-fetch-site": "same-origin" },
        }),
        base,
      ),
    ).toBe(true);
    expect(sameOriginWrite(new Request(base), base)).toBe(true);
  });
});
