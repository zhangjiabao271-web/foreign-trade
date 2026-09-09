import type { Request, Response } from "@playwright/test";

type ObservedResponse = Pick<Response, "url" | "status"> & {
  request(): Pick<Request, "method" | "headers">;
};

export function matchesRoleResponse(
  response: ObservedResponse,
  path: string,
  token: string,
  organizationId: string,
): boolean {
  const request = response.request();
  const headers = request.headers();
  return (
    request.method() === "GET" &&
    response.url().endsWith(path) &&
    response.status() === 200 &&
    headers.authorization === `Bearer ${token}` &&
    headers["x-organization-id"] === organizationId
  );
}
