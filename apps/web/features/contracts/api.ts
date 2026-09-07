"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "../overview/session";
import { uploadDocument } from "../documents/transfer";
import { useUploadRetry } from "../documents/use-upload-retry";

type Schema = components["schemas"];
export type Contract = Schema["ContractResponse"];
export type ContractDocument = Schema["DocumentResponse"];
export type ContractWrite =
  | { action: "create"; body: Schema["ContractCreate"]; key: string }
  | {
      action: "update";
      id: string;
      body: Schema["ContractUpdate"];
      key: string;
    }
  | { action: "sign"; id: string; body: Schema["ContractSign"]; key: string }
  | {
      action: "void";
      id: string;
      body: Schema["ContractCommand"];
      key: string;
    };

export function useContracts(scope: string, orderId: string, cursor?: string) {
  return useQuery({
    queryKey: ["contracts", scope, orderId, cursor],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET(
        "/api/v1/sales-orders/{order_id}/contracts",
        {
          params: { path: { order_id: orderId }, query: { cursor, limit: 10 } },
        },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useContractDocuments(scope: string, orderId: string) {
  return useQuery({
    queryKey: ["contract-documents", scope, orderId],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/documents", {
        params: { query: { target_type: "SALES_ORDER", target_id: orderId } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data.items.filter((d) => d.document_type === "SALES_CONTRACT");
    },
  });
}
export function useContractWrite(scope: string, orderId: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: async (command: ContractWrite) => {
      const client = sessionClient();
      const params = {
        path: {
          order_id: orderId,
          contract_id: "id" in command ? command.id : "",
        },
        header: { "Idempotency-Key": command.key },
      };
      let r;
      switch (command.action) {
        case "create":
          r = await client.POST("/api/v1/sales-orders/{order_id}/contracts", {
            params,
            body: command.body,
          });
          break;
        case "update":
          r = await client.PUT(
            "/api/v1/sales-orders/{order_id}/contracts/{contract_id}",
            { params, body: command.body },
          );
          break;
        case "sign":
          r = await client.POST(
            "/api/v1/sales-orders/{order_id}/contracts/{contract_id}/record-signature",
            { params, body: command.body },
          );
          break;
        case "void":
          r = await client.POST(
            "/api/v1/sales-orders/{order_id}/contracts/{contract_id}/void",
            { params, body: command.body },
          );
          break;
      }
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    onSuccess: async () => {
      await Promise.all([
        cache.invalidateQueries({ queryKey: ["contracts", scope, orderId] }),
        cache.invalidateQueries({ queryKey: ["order-finance"] }),
      ]);
    },
  });
}
export function useContractUpload(scope: string, orderId: string) {
  const cache = useQueryClient();
  const retry = useUploadRetry();
  return useMutation({
    mutationFn: (file: File) =>
      uploadDocument(
        sessionClient(),
        {
          file,
          documentType: "SALES_CONTRACT",
          targetType: "SALES_ORDER",
          targetId: orderId,
        },
        retry(),
      ),
    onSuccess: () =>
      cache.invalidateQueries({
        queryKey: ["contract-documents", scope, orderId],
      }),
  });
}
export function useContractDownload() {
  return useMutation({
    mutationFn: async (input: { documentId: string; versionId: string }) => {
      const r = await sessionClient().POST(
        "/api/v1/documents/{document_id}/versions/{version_id}/download-session",
        {
          params: {
            path: {
              document_id: input.documentId,
              version_id: input.versionId,
            },
          },
        },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      window.location.assign(r.data.download_url);
    },
  });
}
