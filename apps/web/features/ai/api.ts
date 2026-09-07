"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "../overview/session";

export type Run = components["schemas"]["AiRunResponse"];
export type Approval = components["schemas"]["ApprovalResponse"];
export type Intent = components["schemas"]["AiIntent"];

export function useRuns(scope: string, cursor?: string) {
  return useQuery({
    queryKey: ["ai", scope, "runs", cursor],
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/ai/runs", {
        params: { query: { cursor, limit: 10 } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    refetchInterval: (q) =>
      q.state.data?.items.some((r) => ["PENDING", "RUNNING"].includes(r.status))
        ? 2000
        : false,
  });
}
export function useRun(scope: string, id: string) {
  return useQuery({
    queryKey: ["ai", scope, "run", id],
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/ai/runs/{run_id}", {
        params: { path: { run_id: id } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    refetchInterval: (q) =>
      q.state.data && ["PENDING", "RUNNING"].includes(q.state.data.status)
        ? 2000
        : false,
  });
}
export function useCalls(scope: string, id: string, done: boolean) {
  return useQuery({
    queryKey: ["ai", scope, "calls", id, done],
    queryFn: async () => {
      const r = await sessionClient().GET(
        "/api/v1/ai/runs/{run_id}/tool-calls",
        { params: { path: { run_id: id } } },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useApprovals(scope: string, cursor?: string) {
  return useQuery({
    queryKey: ["ai", scope, "approvals", cursor],
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/ai/approvals", {
        params: { query: { cursor, limit: 10 } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useAiCommand(scope: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: async (
      input:
        | {
            action: "run";
            body: components["schemas"]["AiRunCreate"];
            key: string;
          }
        | {
            action: "approve" | "reject";
            id: string;
            body: components["schemas"]["ApprovalDecision"];
          }
        | {
            action: "request";
            id: string;
            body: components["schemas"]["AiApprovalRequest"];
          },
    ) => {
      if (input.action === "run") {
        const r = await sessionClient().POST("/api/v1/ai/runs", {
          body: input.body,
          params: { header: { "idempotency-key": input.key } },
        });
        if (!r.data) throw await parseApiError(r.response, r.error);
        return r.data;
      }
      if (input.action === "request") {
        const r = await sessionClient().POST(
          "/api/v1/ai/runs/{run_id}/request-approval",
          { body: input.body, params: { path: { run_id: input.id } } },
        );
        if (!r.data) throw await parseApiError(r.response, r.error);
        return r.data;
      }
      const path =
        input.action === "approve"
          ? "/api/v1/ai/approvals/{approval_id}/approve"
          : "/api/v1/ai/approvals/{approval_id}/reject";
      const r = await sessionClient().POST(path, {
        body: input.body,
        params: { path: { approval_id: input.id } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    onSuccess: () => cache.invalidateQueries({ queryKey: ["ai", scope] }),
  });
}
