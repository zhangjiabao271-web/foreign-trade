import LogtoClient from "@logto/next/server-actions";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { logtoConfig, sameOriginWrite } from "@/lib/auth/config";

export async function POST(request: Request) {
  try {
    const config = logtoConfig();
    if (!config)
      return NextResponse.json(
        { code: "LOGIN_NOT_CONFIGURED" },
        { status: 503 },
      );
    if (!sameOriginWrite(request, config.baseUrl))
      return NextResponse.json({ code: "ORIGIN_DENIED" }, { status: 403 });
    const url = await new LogtoClient(config).handleSignOut(config.baseUrl);
    (await cookies()).delete("trade-session-marker");
    return NextResponse.redirect(url, 303);
  } catch {
    return NextResponse.json({ code: "LOGOUT_UNAVAILABLE" }, { status: 503 });
  }
}
