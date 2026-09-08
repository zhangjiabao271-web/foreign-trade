import { ApiClientError, parseApiError } from "@trade-workbench/api-client";
import { describe, expect, it } from "vitest";

describe("parseApiError", () => {
  it("preserves sanitized request validation categories and correlation", async () => {
    const problem = {
      type: "https://trade-workbench.local/problems/request-validation-error",
      title: "Invalid request",
      status: 422,
      code: "REQUEST_VALIDATION_ERROR",
      detail: "Check the submitted fields.",
      request_id: "00000000-0000-0000-0000-000000000002",
      errors: [{ location: "body", code: "REQUIRED_VALUE" }],
    };
    const error = await parseApiError(
      new Response(JSON.stringify(problem), {
        status: 422,
        headers: { "Content-Type": "application/problem+json" },
      }),
    );
    expect(error.problem).toEqual(problem);
  });
  it("preserves generated Problem Details returned by openapi-fetch", async () => {
    const problem = {
      type: "https://trade-workbench.local/problems/job-not-found",
      title: "Job not found",
      status: 404,
      code: "JOB_NOT_FOUND",
      detail: "The job was not found.",
      request_id: "00000000-0000-0000-0000-000000000001",
      errors: [],
    };

    const error = await parseApiError(
      new Response(null, { status: 404 }),
      problem,
    );

    expect(error).toBeInstanceOf(ApiClientError);
    expect(error.problem).toEqual(problem);
  });

  it("normalizes a non-JSON server failure", async () => {
    const response = new Response("gateway failure", {
      status: 502,
      headers: { "X-Request-ID": "request-123" },
    });

    const error = await parseApiError(response);

    expect(error.problem.code).toBe("UNEXPECTED_API_ERROR");
    expect(error.problem.request_id).toBe("request-123");
  });
});
