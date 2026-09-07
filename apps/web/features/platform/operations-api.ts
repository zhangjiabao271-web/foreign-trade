"use client";
import { useQuery } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "../overview/session";
export type Operations = components["schemas"]["OperationsResponse"];
export function useOperations(scope: string) {
  return useQuery({
    queryKey: ["operations", scope],
    retry: false,
    refetchInterval: 60_000,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/operations");
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
