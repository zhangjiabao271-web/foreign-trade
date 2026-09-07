import { getAccessToken } from "@logto/next/server-actions";
import {
  businessResource,
  logtoConfig,
  sameOriginWrite,
  testBearerEnabled,
} from "@/lib/auth/config";

const FORWARDED_REQUEST_HEADERS = [
  "accept",
  "content-type",
  "idempotency-key",
  "if-match",
  "x-organization-id",
  "x-request-id",
] as const;

async function proxy(request: Request, path: string[]) {
  if (
    path[0] !== "api" ||
    path[1] !== "v1" ||
    path.some((part) => part === "." || part === ".." || /[\\/]/.test(part))
  ) {
    return Response.json({ code: "INVALID_API_PATH" }, { status: 400 });
  }
  let authorization: string | null = null;
  try {
    const config = logtoConfig();
    if (config) {
      if (!sameOriginWrite(request, config.baseUrl))
        return Response.json({ code: "ORIGIN_DENIED" }, { status: 403 });
      authorization = `Bearer ${await getAccessToken(config, businessResource())}`;
    } else if (testBearerEnabled()) {
      authorization = request.headers.get("authorization");
    }
  } catch {
    return Response.json({ code: "SESSION_EXPIRED" }, { status: 401 });
  }
  if (!authorization)
    return Response.json({ code: "AUTHENTICATION_REQUIRED" }, { status: 401 });
  const apiBaseUrl =
    process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";
  const incomingUrl = new URL(request.url);
  const targetUrl = new URL(`/${path.join("/")}`, apiBaseUrl);
  targetUrl.search = incomingUrl.search;

  const headers = new Headers();
  headers.set("authorization", authorization);
  for (const headerName of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(headerName);
    if (value) headers.set(headerName, value);
  }

  const body =
    request.method === "GET" ? undefined : await request.arrayBuffer();
  const response = await fetch(targetUrl, {
    method: request.method,
    headers,
    body,
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(30_000),
  });
  const responseHeaders = new Headers();
  responseHeaders.set("cache-control", "no-store");
  for (const headerName of ["content-type", "x-request-id"]) {
    const value = response.headers.get(headerName);
    if (value) responseHeaders.set(headerName, value);
  }
  return new Response(response.body, {
    status: response.status,
    headers: responseHeaders,
  });
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, context: RouteContext) {
  return proxy(request, (await context.params).path);
}

export async function POST(request: Request, context: RouteContext) {
  return proxy(request, (await context.params).path);
}

export async function PUT(request: Request, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
