"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "../overview/session";

export type Disclosure = components["schemas"]["AiDisclosureResponse"];
type Command =
  | {
      action: "submit";
      id: string;
      key: string;
      body: components["schemas"]["AiDisclosureSubmit"];
    }
  | {
      action: "decide";
      id: string;
      key: string;
      body: components["schemas"]["AiDisclosureDecision"];
    }
  | {
      action: "revise";
      id: string;
      key: string;
      body: components["schemas"]["AiDisclosureRevision"];
    };

export function useDisclosures(scope: string, cursor?: string) {
  return useQuery({
    queryKey: ["ai", scope, "disclosures", cursor],
    queryFn: async () => {
      const result = await sessionClient().GET("/api/v1/ai/disclosures", {
        params: { query: { cursor, limit: 10 } },
      });
      if (!result.data)
        throw await parseApiError(result.response, result.error);
      return result.data;
    },
  });
}

export function useDisclosureCommand(scope: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: async (command: Command) => {
      const header = { "idempotency-key": command.key };
      const client = sessionClient();
      let result;
      if (command.action === "submit") {
        result = await client.POST(
          "/api/v1/ai/runs/{run_id}/submit-disclosure",
          {
            params: { path: { run_id: command.id }, header },
            body: command.body,
          },
        );
      } else if (command.action === "revise") {
        result = await client.POST(
          "/api/v1/ai/disclosures/{record_id}/revise",
          {
            params: { path: { record_id: command.id }, header },
            body: command.body,
          },
        );
      } else {
        result = await client.POST(
          "/api/v1/ai/disclosures/{record_id}/decide",
          {
            params: { path: { record_id: command.id }, header },
            body: command.body,
          },
        );
      }
      if (!result.data)
        throw await parseApiError(result.response, result.error);
      return result.data;
    },
    onSuccess: () => cache.invalidateQueries({ queryKey: ["ai", scope] }),
  });
}
