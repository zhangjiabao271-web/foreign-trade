"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "../overview/session";
import { uploadDocument } from "../documents/transfer";
import { useUploadRetry } from "../documents/use-upload-retry";

type Schema = components["schemas"];
export type CaseKind = "customs" | "refunds";
export type ExportCase = Schema["CustomsResponse"] | Schema["RefundResponse"];
export type CaseAction =
  "prepare" | "ready" | "submit" | "clear" | "process" | "receive" | "reject";
export type ManualFact = Schema["CaseCommand"] &
  Pick<Schema["ManualSubmission"], "occurred_on" | "external_reference"> & {
    refunded_amount: Extract<
      Schema["RefundReceived"]["refunded_amount"],
      string
    >;
    reason: NonNullable<Schema["CaseCommand"]["reason"]>;
  };

export function useCases(scope: string, kind: CaseKind, cursor?: string) {
  return useQuery({
    queryKey: ["export", scope, kind, "list", cursor],
    queryFn: async () => {
      const r = await sessionClient().GET(
        kind === "customs"
          ? "/api/v1/customs-declarations"
          : "/api/v1/tax-refund-cases",
        { params: { query: { cursor, limit: 20 } } },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useExportCase(scope: string, kind: CaseKind, id: string) {
  return useQuery({
    queryKey: ["export", scope, kind, id],
    refetchInterval: 5000,
    queryFn: async () => {
      const r = await sessionClient().GET(
        kind === "customs"
          ? "/api/v1/customs-declarations/{case_id}"
          : "/api/v1/tax-refund-cases/{case_id}",
        { params: { path: { case_id: id } } },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useCaseActivities(
  scope: string,
  kind: CaseKind,
  id: string,
  cursor?: string,
) {
  return useQuery({
    queryKey: ["export", scope, kind, id, "activities", cursor],
    queryFn: async () => {
      const r = await sessionClient().GET(
        kind === "customs"
          ? "/api/v1/customs-declarations/{case_id}/activities"
          : "/api/v1/tax-refund-cases/{case_id}/activities",
        { params: { path: { case_id: id }, query: { cursor, limit: 20 } } },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useRefreshExport() {
  const cache = useQueryClient();
  return async () => {
    await Promise.all([
      cache.invalidateQueries({ queryKey: ["export"] }),
      cache.invalidateQueries({ queryKey: ["overview"] }),
    ]);
  };
}
export function useCreateCase() {
  const refresh = useRefreshExport();
  return useMutation({
    mutationFn: async (
      input:
        | { kind: "customs"; body: Schema["CustomsCreate"]; key: string }
        | { kind: "refunds"; body: Schema["RefundCreate"]; key: string },
    ) => {
      const params = { header: { "Idempotency-Key": input.key } };
      const r =
        input.kind === "customs"
          ? await sessionClient().POST("/api/v1/customs-declarations", {
              params,
              body: input.body,
            })
          : await sessionClient().POST("/api/v1/tax-refund-cases", {
              params,
              body: input.body,
            });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    onSuccess: refresh,
  });
}
export function useCaseCommand(kind: CaseKind, id: string) {
  const refresh = useRefreshExport();
  return useMutation({
    mutationFn: async ({
      action,
      fact,
    }: {
      action: CaseAction;
      fact: ManualFact;
    }) => {
      const client = sessionClient();
      const params = { path: { case_id: id } };
      const basic = {
        expected_version: fact.expected_version,
        ...(fact.reason ? { reason: fact.reason } : {}),
      };
      let r;
      if (action === "submit") {
        const body = {
          ...basic,
          external_reference: fact.external_reference,
          occurred_on: fact.occurred_on,
        };
        r =
          kind === "customs"
            ? await client.POST(
                "/api/v1/customs-declarations/{case_id}/submit",
                { params, body },
              )
            : await client.POST("/api/v1/tax-refund-cases/{case_id}/submit", {
                params,
                body,
              });
      } else if (action === "clear") {
        r = await client.POST("/api/v1/customs-declarations/{case_id}/clear", {
          params,
          body: { ...basic, occurred_on: fact.occurred_on },
        });
      } else if (action === "receive") {
        r = await client.POST("/api/v1/tax-refund-cases/{case_id}/receive", {
          params,
          body: {
            ...basic,
            occurred_on: fact.occurred_on,
            refunded_amount: fact.refunded_amount,
          },
        });
      } else if (action === "reject") {
        const body = { ...basic, reason: fact.reason };
        r =
          kind === "customs"
            ? await client.POST(
                "/api/v1/customs-declarations/{case_id}/reject",
                { params, body },
              )
            : await client.POST("/api/v1/tax-refund-cases/{case_id}/reject", {
                params,
                body,
              });
      } else {
        const paths = {
          customs: {
            prepare: "/api/v1/customs-declarations/{case_id}/prepare",
            ready: "/api/v1/customs-declarations/{case_id}/ready",
          },
          refunds: {
            prepare: "/api/v1/tax-refund-cases/{case_id}/prepare",
            ready: "/api/v1/tax-refund-cases/{case_id}/ready",
          },
        } as const;
        const path =
          action === "process"
            ? "/api/v1/tax-refund-cases/{case_id}/process"
            : paths[kind][action];
        r = await client.POST(path, { params, body: basic });
      }
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    onSuccess: refresh,
  });
}
export function useCaseDocuments(scope: string, kind: CaseKind, id: string) {
  return useQuery({
    queryKey: ["export", scope, kind, id, "documents"],
    refetchInterval: 3000,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/documents", {
        params: {
          query: {
            target_type:
              kind === "customs" ? "CUSTOMS_DECLARATION" : "TAX_REFUND_CASE",
            target_id: id,
          },
        },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useCaseUpload(kind: CaseKind, id: string) {
  const refresh = useRefreshExport();
  const retry = useUploadRetry();
  return useMutation({
    mutationFn: (input: {
      file: File;
      documentType: Schema["DocumentType"];
      replacement?: { documentId: string; expectedVersion: number };
    }) =>
      uploadDocument(
        sessionClient(),
        {
          ...input,
          targetType:
            kind === "customs" ? "CUSTOMS_DECLARATION" : "TAX_REFUND_CASE",
          targetId: id,
        },
        retry(),
      ),
    onSuccess: refresh,
  });
}

export function useScheduleFollowUp(kind: CaseKind, id: string) {
  const refresh = useRefreshExport();
  return useMutation({
    mutationFn: async (body: Schema["FollowUpSchedule"]) => {
      const r = await sessionClient().POST(
        kind === "customs"
          ? "/api/v1/customs-declarations/{case_id}/schedule-follow-up"
          : "/api/v1/tax-refund-cases/{case_id}/schedule-follow-up",
        { params: { path: { case_id: id } }, body },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    onSuccess: refresh,
  });
}
