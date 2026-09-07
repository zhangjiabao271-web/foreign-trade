"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "../overview/session";
type Schema = components["schemas"];
export type Payable = Schema["PayableResponse"];
export type SupplierPayment = Schema["SupplierPaymentResponse"];
export type SupplierWrite =
  | { action: "payable"; body: Schema["PayableCreate"]; key: string }
  | { action: "payment"; body: Schema["SupplierPaymentCreate"]; key: string }
  | {
      action: "allocate";
      id: string;
      body: Schema["SupplierPaymentAllocate"];
      key: string;
    }
  | {
      action: "void" | "reverse";
      id: string;
      body: Schema["SupplierVersionCommand"];
      key: string;
    };

export function usePayables(
  scope: string,
  purchaseId: string,
  cursor?: string,
) {
  return useQuery({
    queryKey: ["payables", scope, purchaseId, cursor],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/payables", {
        params: { query: { purchase_order_id: purchaseId, cursor, limit: 20 } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useSupplierPayments(
  scope: string,
  supplierId: string,
  currency: string,
  cursor?: string,
) {
  return useQuery({
    queryKey: ["supplier-payments", scope, supplierId, currency, cursor],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/supplier-payments", {
        params: {
          query: {
            supplier_company_id: supplierId,
            currency_code: currency,
            cursor,
            limit: 20,
          },
        },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useSupplierWrite(scope: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: async (command: SupplierWrite) => {
      const client = sessionClient();
      const header = { "Idempotency-Key": command.key };
      let r;
      switch (command.action) {
        case "payable":
          r = await client.POST("/api/v1/payables", {
            params: { header },
            body: command.body,
          });
          break;
        case "payment":
          r = await client.POST("/api/v1/supplier-payments", {
            params: { header },
            body: command.body,
          });
          break;
        case "void":
          r = await client.POST("/api/v1/payables/{payable_id}/void", {
            params: { header, path: { payable_id: command.id } },
            body: command.body,
          });
          break;
        case "allocate":
          r = await client.POST(
            "/api/v1/supplier-payments/{payment_id}/allocate",
            {
              params: { header, path: { payment_id: command.id } },
              body: command.body,
            },
          );
          break;
        case "reverse":
          r = await client.POST(
            "/api/v1/supplier-payments/{payment_id}/reverse",
            {
              params: { header, path: { payment_id: command.id } },
              body: command.body,
            },
          );
          break;
      }
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    onSuccess: async () => {
      await Promise.all([
        cache.invalidateQueries({ queryKey: ["payables", scope] }),
        cache.invalidateQueries({ queryKey: ["supplier-payments", scope] }),
        cache.invalidateQueries({ queryKey: ["order-finance"] }),
      ]);
    },
  });
}
