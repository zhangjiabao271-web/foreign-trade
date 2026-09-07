export const dynamic = "force-dynamic";

export async function GET() {
  const apiBaseUrl =
    process.env.INTERNAL_API_BASE_URL ?? "http://localhost:8000";
  let api: "ready" | "degraded" | "unavailable" = "unavailable";

  try {
    const response = await fetch(`${apiBaseUrl}/health/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2_500),
    });
    if (response.ok) {
      api = "ready";
    } else if (response.status === 503) {
      api = "degraded";
    }
  } catch {
    api = "unavailable";
  }

  return Response.json({
    web: "ready",
    api,
    checked_at: new Date().toISOString(),
  });
}
