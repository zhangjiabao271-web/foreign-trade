"use client";

import {
  createTradeApiClient,
  parseApiError,
  type components,
} from "@trade-workbench/api-client";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useRef } from "react";
import { collectCursorItems } from "../../lib/cursor-pages";

import { sessionKeys } from "../leads/api";

export type SalesOrder = components["schemas"]["SalesOrderResponse"];
export type SalesOrderCreate = components["schemas"]["SalesOrderCreate"];
export type SalesOrderConfirm = components["schemas"]["SalesOrderConfirm"];
export type PurchaseOrder = components["schemas"]["PurchaseOrderResponse"];
export type PurchaseOrderCreate = components["schemas"]["PurchaseOrderCreate"];
export type PurchaseOrderDecision =
  components["schemas"]["PurchaseOrderDecision"];
export type PurchaseOrderConfirm =
  components["schemas"]["PurchaseOrderConfirm"];
export type PurchaseOrderReceive =
  components["schemas"]["PurchaseOrderReceive"];
export type PurchaseOrderClose = components["schemas"]["PurchaseOrderClose"];
export type PurchaseOrderCancel = components["schemas"]["PurchaseOrderCancel"];
export type PurchaseOrderAmend = components["schemas"]["PurchaseOrderAmend"];

function storedValue(key: string) {
  return typeof window === "undefined"
    ? undefined
    : (window.localStorage.getItem(key) ?? undefined);
}

function tradeApi() {
  return createTradeApiClient({
    baseUrl: `${typeof window === "undefined" ? "http://localhost:3000" : window.location.origin}/api/backend`,
    getAccessToken: () => storedValue(sessionKeys.accessToken),
    getOrganizationId: () => storedValue(sessionKeys.organizationId),
  });
}

export function useSalesOrders(enabled: boolean) {
  const queryClient = useQueryClient();
  const query = useInfiniteQuery({
    queryKey: ["sales-orders", "pages"],
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const { data, error, response } = await tradeApi().GET(
        "/api/v1/sales-orders",
        { params: { query: { limit: 50, cursor: pageParam } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    getNextPageParam: (page) =>
      page.has_more ? (page.next_cursor ?? undefined) : undefined,
    select: (data) => collectCursorItems(data),
  });
  return {
    ...query,
    restart: () =>
      queryClient.resetQueries({ queryKey: ["sales-orders", "pages"] }),
  };
}

export function useSalesOrder(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["sales-order", id],
    enabled: enabled && Boolean(id),
    queryFn: async () => {
      const { data, error, response } = await tradeApi().GET(
        "/api/v1/sales-orders/{sales_order_id}",
        { params: { path: { sales_order_id: id! } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
  });
}

export function useRefreshOrders(id?: string) {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["sales-orders"] }),
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] }),
      queryClient.invalidateQueries({ queryKey: ["purchase-activities"] }),
      id
        ? queryClient.invalidateQueries({ queryKey: ["sales-order", id] })
        : Promise.resolve(),
    ]);
  };
}

export function useCreateSalesOrder() {
  const refresh = useRefreshOrders();
  return useMutation({
    mutationFn: async ({
      body,
      key,
    }: {
      body: SalesOrderCreate;
      key: string;
    }) => {
      const { data, error, response } = await tradeApi().POST(
        "/api/v1/sales-orders",
        { body, params: { header: { "Idempotency-Key": key } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    onSuccess: refresh,
  });
}

export function useConfirmSalesOrder(id: string) {
  const refresh = useRefreshOrders(id);
  const retry = useRef<{ payload: string; key: string } | null>(null);
  return useMutation({
    mutationFn: async (body: SalesOrderConfirm) => {
      const payload = JSON.stringify({ id, body });
      if (retry.current?.payload !== payload)
        retry.current = { payload, key: crypto.randomUUID() };
      const { data, error, response } = await tradeApi().POST(
        "/api/v1/sales-orders/{sales_order_id}/confirm",
        {
          params: {
            path: { sales_order_id: id },
            header: { "Idempotency-Key": retry.current.key },
          },
          body,
        },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    onSuccess: refresh,
  });
}

export function usePurchaseOrders(enabled: boolean, salesOrderId?: string) {
  const queryClient = useQueryClient();
  const queryKey = ["purchase-orders", "pages", salesOrderId];
  const query = useInfiniteQuery({
    queryKey,
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const { data, error, response } = await tradeApi().GET(
        "/api/v1/purchase-orders",
        {
          params: {
            query: {
              limit: 50,
              cursor: pageParam,
              sales_order_id: salesOrderId,
            },
          },
        },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    getNextPageParam: (page) =>
      page.has_more ? (page.next_cursor ?? undefined) : undefined,
    select: (data) => collectCursorItems(data),
  });
  return { ...query, restart: () => queryClient.resetQueries({ queryKey }) };
}

export function useCreatePurchaseOrder() {
  const refresh = useRefreshOrders();
  return useMutation({
    mutationFn: async ({
      body,
      key,
    }: {
      body: PurchaseOrderCreate;
      key: string;
    }) => {
      const { data, error, response } = await tradeApi().POST(
        "/api/v1/purchase-orders",
        { body, headers: { "Idempotency-Key": key } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    onSuccess: refresh,
  });
}

export type PurchaseCommand = "approve" | "send";

export function usePurchaseOrderCommand(id: string) {
  const refresh = useRefreshOrders();
  const retry = useRef<{ payload: string; key: string } | null>(null);
  return useMutation({
    mutationFn: async (
      input:
        | { command: PurchaseCommand; body: PurchaseOrderDecision }
        | { command: "confirm"; body: PurchaseOrderConfirm },
    ) => {
      const payload = JSON.stringify({ id, input });
      if (retry.current?.payload !== payload)
        retry.current = { payload, key: crypto.randomUUID() };
      const params = {
        path: { purchase_order_id: id },
        header: { "Idempotency-Key": retry.current.key },
      };
      if (input.command === "confirm") {
        const { data, error, response } = await tradeApi().POST(
          "/api/v1/purchase-orders/{purchase_order_id}/confirm",
          { params, body: input.body },
        );
        if (!data) throw await parseApiError(response, error);
        return data;
      }
      const path =
        `/api/v1/purchase-orders/{purchase_order_id}/${input.command}` as
          | "/api/v1/purchase-orders/{purchase_order_id}/approve"
          | "/api/v1/purchase-orders/{purchase_order_id}/send";
      const { data, error, response } = await tradeApi().POST(path, {
        params,
        body: input.body,
      });
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    onSuccess: refresh,
  });
}

export function usePurchaseReceiptCommand(id: string) {
  const refresh = useRefreshOrders();
  return useMutation({
    mutationFn: async (
      input:
        | { command: "receive"; body: PurchaseOrderReceive; key: string }
        | { command: "close"; body: PurchaseOrderClose; key: string },
    ) => {
      const headers = { "Idempotency-Key": input.key };
      const params = { path: { purchase_order_id: id }, header: headers };
      const result =
        input.command === "receive"
          ? await tradeApi().POST(
              "/api/v1/purchase-orders/{purchase_order_id}/receive",
              { params, headers, body: input.body },
            )
          : await tradeApi().POST(
              "/api/v1/purchase-orders/{purchase_order_id}/close",
              { params, headers, body: input.body },
            );
      if (!result.data)
        throw await parseApiError(result.response, result.error);
      return result.data;
    },
    onSuccess: refresh,
  });
}

export function usePurchaseActivities(id: string, offset: number) {
  return useQuery({
    queryKey: ["purchase-activities", id, offset],
    retry: false,
    queryFn: async () => {
      const r = await tradeApi().GET(
        "/api/v1/purchase-orders/{purchase_order_id}/activities",
        {
          params: {
            path: { purchase_order_id: id },
            query: { offset, limit: 11 },
          },
        },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}

export function usePurchaseChangeCommand(id: string) {
  const refresh = useRefreshOrders();
  return useMutation({
    mutationFn: async (
      input:
        | { command: "cancel"; body: PurchaseOrderCancel; key: string }
        | { command: "amend"; body: PurchaseOrderAmend; key: string },
    ) => {
      const params = {
        path: { purchase_order_id: id },
        header: { "Idempotency-Key": input.key },
      };
      const result =
        input.command === "cancel"
          ? await tradeApi().POST(
              "/api/v1/purchase-orders/{purchase_order_id}/cancel",
              { params, body: input.body },
            )
          : await tradeApi().POST(
              "/api/v1/purchase-orders/{purchase_order_id}/amend",
              { params, body: input.body },
            );
      if (!result.data)
        throw await parseApiError(result.response, result.error);
      return result.data;
    },
    onSuccess: refresh,
  });
}
