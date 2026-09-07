import type { LogtoNextConfig } from "@logto/next";

export function testBearerEnabled() {
  return (
    process.env.E2E_AUTH_MODE === "bearer" &&
    process.env.NODE_ENV !== "production"
  );
}

export function logtoConfig(): LogtoNextConfig | null {
  const {
    LOGTO_ENDPOINT,
    LOGTO_APP_ID,
    LOGTO_APP_SECRET,
    LOGTO_COOKIE_SECRET,
    APP_BASE_URL,
  } = process.env;
  if (
    !LOGTO_ENDPOINT ||
    !LOGTO_APP_ID ||
    !LOGTO_APP_SECRET ||
    !LOGTO_COOKIE_SECRET ||
    !APP_BASE_URL
  )
    return null;
  const endpoint = new URL(LOGTO_ENDPOINT);
  const base = new URL(APP_BASE_URL);
  const localHttp = process.env.LOCAL_AUTH_ALLOW_HTTP === "true";
  for (const url of [endpoint, base]) {
    const local = ["localhost", "127.0.0.1", "logto.localhost"].includes(
      url.hostname,
    );
    if (
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      (url.protocol !== "https:" &&
        !(localHttp && local && url.protocol === "http:"))
    ) {
      throw new Error("Invalid authentication endpoint configuration");
    }
  }
  if (LOGTO_COOKIE_SECRET.length < 32 || base.pathname !== "/") {
    throw new Error("Invalid authentication session configuration");
  }
  return {
    endpoint: endpoint.toString().replace(/\/$/, ""),
    appId: LOGTO_APP_ID,
    appSecret: LOGTO_APP_SECRET,
    cookieSecret: LOGTO_COOKIE_SECRET,
    baseUrl: base.origin,
    cookieSecure: base.protocol === "https:",
    resources: [businessResource()],
  };
}

export function businessResource() {
  return process.env.OIDC_AUDIENCE ?? "https://api.trade-workbench.local";
}

export function sameOriginWrite(request: Request, baseUrl: string) {
  if (["GET", "HEAD", "OPTIONS"].includes(request.method)) return true;
  return (
    request.headers.get("origin") === new URL(baseUrl).origin &&
    request.headers.get("sec-fetch-site") !== "cross-site"
  );
}
