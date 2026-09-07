"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "../overview/session";

export type OutboxEvent = components["schemas"]["OutboxEventResponse"];
export function useDeadEvents(scope: string, offset: number) {
  return useQuery({
    queryKey: ["dead-events", scope, offset],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/outbox/dead", {
        params: { query: { offset, limit: 10 } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useReplayEvent(scope: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: async ({
      event,
      reason,
    }: {
      event: OutboxEvent;
      reason: string;
    }) => {
      const r = await sessionClient().POST("/api/v1/outbox/{event_id}/replay", {
        params: { path: { event_id: event.id } },
        body: { reason, expected_version: event.version },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    onSuccess: () =>
      cache.invalidateQueries({ queryKey: ["dead-events", scope] }),
  });
}
