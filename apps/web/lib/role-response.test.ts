import { describe, expect, it } from "vitest";
import { matchesRoleResponse } from "../e2e/role-response";

const path = "/quotations/fixture-order";

function response(
  overrides: {
    token?: string;
    organization?: string;
    method?: string;
    status?: number;
    path?: string;
  } = {},
) {
  return {
    url: () => `http://127.0.0.1:3100/api/backend${overrides.path ?? path}`,
    status: () => overrides.status ?? 200,
    request: () => ({
      method: () => overrides.method ?? "GET",
      headers: () => ({
        authorization: `Bearer ${overrides.token ?? "fixture-manager"}`,
        "x-organization-id": overrides.organization ?? "fixture-org",
      }),
    }),
  };
}

describe("role response correlation", () => {
  it("ignores an earlier sales read even when it arrives before the manager read", () => {
    const oldRead = response({ token: "fixture-sales" });
    const managerRead = response();
    const matches = [oldRead, managerRead].filter((item) =>
      matchesRoleResponse(item, path, "fixture-manager", "fixture-org"),
    );
    expect(matches).toEqual([managerRead]);
  });

  it.each([
    { organization: "another-org" },
    { method: "POST" },
    { status: 401 },
    { path: "/quotations/another-order" },
  ])("rejects a response outside the selected request: %j", (overrides) => {
    expect(
      matchesRoleResponse(
        response(overrides),
        path,
        "fixture-manager",
        "fixture-org",
      ),
    ).toBe(false);
  });
});
