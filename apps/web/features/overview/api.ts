"use client";
import { useQuery } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "./session";
export type QueueKind = components["schemas"]["QueueKind"];
export function useMemberContext(scope: string) {
  return useQuery({
    queryKey: ["member-context", scope],
    enabled: Boolean(scope),
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/me/context");
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useActionQueue(
  scope: string,
  queue: QueueKind,
  offset: number,
) {
  return useQuery({
    queryKey: ["overview", scope, queue, offset],
    retry: false,
    refetchInterval: 60_000,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/overview/{queue}", {
        params: { path: { queue }, query: { offset, limit: 5 } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
