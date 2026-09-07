import { z } from "zod";

const platformHealthSchema = z.object({
  web: z.literal("ready"),
  api: z.enum(["ready", "degraded", "unavailable"]),
  checked_at: z.string(),
});

export type PlatformHealth = z.infer<typeof platformHealthSchema>;

export async function getPlatformHealth(
  signal?: AbortSignal,
): Promise<PlatformHealth> {
  const response = await fetch("/api/platform-health", { signal });
  if (!response.ok) {
    throw new Error("PLATFORM_HEALTH_UNAVAILABLE");
  }

  return platformHealthSchema.parse(await response.json());
}
