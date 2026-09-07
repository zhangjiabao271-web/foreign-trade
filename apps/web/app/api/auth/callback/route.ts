import { randomUUID } from "node:crypto";
import LogtoClient from "@logto/next/server-actions";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { logtoConfig } from "@/lib/auth/config";

export async function GET(request: Request) {
  try {
    const config = logtoConfig();
    if (!config)
      return NextResponse.json(
        { code: "LOGIN_NOT_CONFIGURED" },
        { status: 503 },
      );
    // Use the configured origin, not an untrusted forwarded Host header.
    const callback = new URL("/api/auth/callback", config.baseUrl);
    callback.search = new URL(request.url).search;
    await new LogtoClient(config).handleSignInCallback(callback.toString());
    (await cookies()).set("trade-session-marker", randomUUID(), {
      httpOnly: true,
      secure: config.cookieSecure,
      sameSite: "lax",
      path: "/",
    });
    return NextResponse.redirect(new URL("/", config.baseUrl));
  } catch {
    return NextResponse.json(
      { code: "LOGIN_CALLBACK_INVALID" },
      { status: 400 },
    );
  }
}
