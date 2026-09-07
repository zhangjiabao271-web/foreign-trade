import type { components } from "./schema";

export type ProblemDetails = components["schemas"]["ProblemDetails"];

export class ApiClientError extends Error {
  constructor(
    readonly problem: ProblemDetails,
    options?: ErrorOptions,
  ) {
    super(problem.detail, options);
    this.name = "ApiClientError";
  }
}

function isProblemDetails(value: unknown): value is ProblemDetails {
  return (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    typeof value.code === "string" &&
    "type" in value &&
    typeof value.type === "string" &&
    "title" in value &&
    typeof value.title === "string" &&
    "detail" in value &&
    typeof value.detail === "string" &&
    "status" in value &&
    typeof value.status === "number" &&
    "request_id" in value &&
    typeof value.request_id === "string" &&
    "errors" in value &&
    Array.isArray(value.errors)
  );
}

export async function parseApiError(
  response: Response,
  parsedBody?: unknown,
): Promise<ApiClientError> {
  const body: unknown =
    parsedBody ??
    (await response
      .clone()
      .json()
      .catch(() => null));
  if (isProblemDetails(body)) {
    return new ApiClientError(body);
  }
  const requestId = response.headers.get("X-Request-ID") ?? "unknown";
  return new ApiClientError({
    type: "about:blank",
    title: "Unexpected API error",
    status: response.status,
    code: "UNEXPECTED_API_ERROR",
    detail: `The API returned HTTP ${response.status}.`,
    request_id: requestId,
    errors: [],
  });
}
