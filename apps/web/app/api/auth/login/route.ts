import LogtoClient from "@logto/next/server-actions";
import { NextResponse } from "next/server";
import { logtoConfig } from "@/lib/auth/config";

export async function GET() {
  try {
    const config = logtoConfig();
    if (!config)
      return NextResponse.json(
        { code: "LOGIN_NOT_CONFIGURED" },
        { status: 503 },
      );
    const { url } = await new LogtoClient(config).handleSignIn({
      redirectUri: `${config.baseUrl}/api/auth/callback`,
    });
    return NextResponse.redirect(url);
  } catch {
    return NextResponse.json({ code: "LOGIN_UNAVAILABLE" }, { status: 503 });
  }
}
