import { getAccessToken, getLogtoContext } from "@logto/next/server-actions";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  businessResource,
  logtoConfig,
  testBearerEnabled,
} from "@/lib/auth/config";

export async function GET() {
  const headers = { "Cache-Control": "no-store" };
  try {
    const config = logtoConfig();
    if (!config)
      return NextResponse.json(
        {
          configured: false,
          authenticated: false,
          test_bearer: testBearerEnabled(),
        },
        { headers },
      );
    const context = await getLogtoContext(config);
    if (!context.isAuthenticated)
      return NextResponse.json(
        { configured: true, authenticated: false },
        { headers },
      );
    const token = await getAccessToken(config, businessResource());
    const response = await fetch(
      new URL(
        "/api/v1/me/organizations",
        process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000",
      ),
      {
        headers: { authorization: `Bearer ${token}` },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(10_000),
      },
    );
    if (!response.ok)
      return NextResponse.json(
        {
          configured: true,
          authenticated: false,
          code: "BUSINESS_ACCESS_DENIED",
        },
        { status: response.status, headers },
      );
    const marker = (await cookies()).get("trade-session-marker")?.value;
    if (!marker)
      return NextResponse.json(
        { configured: true, authenticated: false },
        { headers },
      );
    return NextResponse.json(
      {
        configured: true,
        authenticated: true,
        marker,
        organizations: await response.json(),
      },
      { headers },
    );
  } catch {
    return NextResponse.json(
      { code: "SESSION_UNAVAILABLE" },
      { status: 503, headers },
    );
  }
}
