import { afterEach, expect, it, vi } from "vitest";
import { PUT } from "../../app/api/backend/[...path]/route";

vi.mock("@logto/next/server-actions", () => ({
  getAccessToken: vi.fn(async () => "fixture-server-token"),
}));
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});
function configure() {
  vi.stubEnv("LOGTO_ENDPOINT", "https://identity.example.test");
  vi.stubEnv("APP_BASE_URL", "https://trade.example.test");
  vi.stubEnv("LOGTO_APP_ID", "fixture-app");
  vi.stubEnv("LOGTO_APP_SECRET", "fixture-secret");
  vi.stubEnv(
    "LOGTO_COOKIE_SECRET",
    "fixture-cookie-secret-at-least-32-characters",
  );
  vi.stubEnv("INTERNAL_API_BASE_URL", "http://api:8000");
}
const context = {
  params: Promise.resolve({
    path: ["api", "v1", "companies", "fixture-company"],
  }),
};
it("forwards PUT body, tenant and command key using the server session", async () => {
  configure();
  const fetch = vi.fn(async () => Response.json({ id: "fixture-company" }));
  vi.stubGlobal("fetch", fetch);
  const body = JSON.stringify({
    name: "Company",
    expected_version: 3,
    reason: "Verified",
  });
  const response = await PUT(
    new Request(
      "https://trade.example.test/api/backend/api/v1/companies/fixture-company",
      {
        method: "PUT",
        body,
        headers: {
          origin: "https://trade.example.test",
          "content-type": "application/json",
          "x-organization-id": "fixture-org",
          "idempotency-key": "fixture-key",
          authorization: "Bearer ignored-browser-token",
        },
      },
    ),
    context,
  );
  expect(response.status).toBe(200);
  const [, options] = fetch.mock.calls[0] as unknown as [URL, RequestInit];
  expect(options.method).toBe("PUT");
  expect(new TextDecoder().decode(options.body as ArrayBuffer)).toBe(body);
  const headers = new Headers(options.headers);
  expect(headers.get("authorization")).toBe("Bearer fixture-server-token");
  expect(headers.get("x-organization-id")).toBe("fixture-org");
  expect(headers.get("idempotency-key")).toBe("fixture-key");
});
it("rejects cross-origin PUT before calling the backend", async () => {
  configure();
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const response = await PUT(
    new Request(
      "https://trade.example.test/api/backend/api/v1/companies/fixture-company",
      {
        method: "PUT",
        headers: { origin: "https://attacker.example.test" },
        body: "{}",
      },
    ),
    context,
  );
  expect(response.status).toBe(403);
  expect(fetch).not.toHaveBeenCalled();
});
