"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "../overview/session";

export type SupplierLink = components["schemas"]["SupplierLinkResponse"];
export type SupplierCreate = components["schemas"]["SupplierLinkCreate"];
export type SupplierUpdate = components["schemas"]["SupplierLinkUpdate"];
export function useProducts(scope: string, query: string, cursor?: string) {
  return useQuery({
    queryKey: ["catalog-products", scope, query, cursor],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/products", {
        params: { query: { query, limit: 50, cursor } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useProduct(scope: string, id: string) {
  return useQuery({
    queryKey: ["catalog-product", scope, id],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET("/api/v1/products/{product_id}", {
        params: { path: { product_id: id } },
      });
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useSupplierLinks(scope: string, id: string, cursor?: string) {
  return useQuery({
    queryKey: ["supplier-links", scope, id, cursor],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET(
        "/api/v1/products/{product_id}/supplier-links",
        { params: { path: { product_id: id }, query: { cursor, limit: 20 } } },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useSupplierHistory(scope: string, id: string, offset: number) {
  return useQuery({
    queryKey: ["supplier-history", scope, id, offset],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET(
        "/api/v1/products/{product_id}/supplier-links/activities",
        { params: { path: { product_id: id }, query: { offset, limit: 10 } } },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
type Write = { key: string } & (
  | { kind: "create"; body: SupplierCreate }
  | { kind: "update"; linkId: string; body: SupplierUpdate }
);
export function useWriteSupplier(scope: string, id: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: async (command: Write) => {
      const params = {
        path: { product_id: id },
        header: { "Idempotency-Key": command.key },
      };
      if (command.kind === "create") {
        const r = await sessionClient().POST(
          "/api/v1/products/{product_id}/supplier-links",
          { params, body: command.body },
        );
        if (!r.data) throw await parseApiError(r.response, r.error);
        return r.data;
      }
      const r = await sessionClient().PUT(
        "/api/v1/products/{product_id}/supplier-links/{link_id}",
        {
          params: {
            ...params,
            path: { ...params.path, link_id: command.linkId },
          },
          body: command.body,
        },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    onSuccess: async () => {
      await Promise.all(
        ["supplier-links", "supplier-history"].map((name) =>
          cache.invalidateQueries({ queryKey: [name, scope, id] }),
        ),
      );
    },
  });
}
