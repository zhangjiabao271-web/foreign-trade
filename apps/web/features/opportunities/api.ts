"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "../overview/session";

export type Opportunity = components["schemas"]["OpportunityResponse"];
export type OpportunityStatus = components["schemas"]["OpportunityStatus"];
export type OpportunityCommand = components["schemas"]["OpportunityCommand"];
export type Command = "start-negotiation" | "mark-lost";

export function useOpportunities(
  scope: string,
  status?: OpportunityStatus,
  cursor?: string,
) {
  return useQuery({
    queryKey: ["opportunities", scope, status, cursor],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/opportunities", {
        params: { query: { status, cursor, limit: 20 } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useOpportunity(scope: string, id: string) {
  return useQuery({
    queryKey: ["opportunity", scope, id],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET(
        "/api/v1/opportunities/{opportunity_id}",
        { params: { path: { opportunity_id: id } } },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useOpportunityHistory(
  scope: string,
  id: string,
  offset: number,
) {
  return useQuery({
    queryKey: ["opportunity-history", scope, id, offset],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET(
        "/api/v1/opportunities/{opportunity_id}/activities",
        {
          params: {
            path: { opportunity_id: id },
            query: { offset, limit: 10 },
          },
        },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useOpportunityCommand(scope: string, id: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: async ({
      command,
      body,
      key,
    }: {
      command: Command;
      body: OpportunityCommand;
      key: string;
    }) => {
      const r = await sessionClient().POST(
        "/api/v1/opportunities/{opportunity_id}/{command}",
        {
          params: {
            path: { opportunity_id: id, command },
            header: { "Idempotency-Key": key },
          },
          body,
        },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    onSuccess: async () => {
      await Promise.all(
        ["opportunity", "opportunities", "opportunity-history", "overview"].map(
          (name) => cache.invalidateQueries({ queryKey: [name, scope] }),
        ),
      );
    },
  });
}
