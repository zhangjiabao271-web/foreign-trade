"use client";

import {
  createTradeApiClient,
  parseApiError,
  type components,
} from "@trade-workbench/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { sessionKeys } from "../leads/api";

type Schema = components["schemas"];
export type Receivable = Schema["ReceivableResponse"];
export type Payment = Schema["PaymentResponse"];
export type Task = Schema["TaskResponse"];

function organization() {
  return window.localStorage.getItem(sessionKeys.organizationId) ?? "";
}
function api() {
  return createTradeApiClient({
    baseUrl: window.location.origin + "/api/backend",
    getAccessToken: () =>
      window.localStorage.getItem(sessionKeys.accessToken) ?? undefined,
    getOrganizationId: () => organization() || undefined,
  });
}

export function useOrderFinance(orderId: string) {
  return useQuery({
    queryKey: ["order-finance", organization(), orderId],
    queryFn: async () => {
      const client = api();
      const [ar, tasks, activities] = await Promise.all([
        client.GET("/api/v1/receivables", {
          params: { query: { sales_order_id: orderId, limit: 100 } },
        }),
        client.GET("/api/v1/sales-orders/{order_id}/tasks", {
          params: { path: { order_id: orderId } },
        }),
        client.GET("/api/v1/sales-orders/{order_id}/activities", {
          params: { path: { order_id: orderId }, query: { limit: 100 } },
        }),
      ]);
      if (!ar.data) throw await parseApiError(ar.response, ar.error);
      if (!tasks.data) throw await parseApiError(tasks.response, tasks.error);
      if (!activities.data)
        throw await parseApiError(activities.response, activities.error);
      return {
        receivables: ar.data.items,
        tasks: tasks.data.items,
        activities: activities.data.items,
      };
    },
  });
}

export function useCustomerPayments(
  companyId: string,
  currencyCode: string,
  query: string,
  cursor?: string,
) {
  return useQuery({
    queryKey: [
      "customer-payments",
      organization(),
      companyId,
      currencyCode,
      query,
      cursor,
    ],
    retry: false,
    queryFn: async () => {
      const result = await api().GET("/api/v1/payments", {
        params: {
          query: {
            company_id: companyId,
            currency_code: currencyCode,
            query,
            cursor,
            limit: 20,
          },
        },
      });
      if (!result.data)
        throw await parseApiError(result.response, result.error);
      return result.data;
    },
  });
}

type Command =
  | { kind: "generate"; body: Schema["ReceivableGenerate"] }
  | { kind: "record"; body: Schema["PaymentCreate"]; key: string }
  | {
      kind: "allocate";
      paymentId: string;
      body: Schema["PaymentAllocate"];
      key: string;
    }
  | { kind: "reverse"; paymentId: string; body: Schema["PaymentReverse"] }
  | { kind: "task"; taskId: string; body: Schema["TaskComplete"] }
  | { kind: "complete"; body: Schema["SalesOrderComplete"] };

export function useFinanceCommand(orderId: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: async (command: Command) => {
      const client = api();
      const orderPath = { sales_order_id: orderId };
      let result;
      switch (command.kind) {
        case "generate":
          result = await client.POST(
            "/api/v1/sales-orders/{sales_order_id}/generate-receivables",
            { params: { path: orderPath }, body: command.body },
          );
          break;
        case "record":
          result = await client.POST("/api/v1/payments", {
            params: { header: { "Idempotency-Key": command.key } },
            body: command.body,
          });
          break;
        case "allocate":
          result = await client.POST("/api/v1/payments/{payment_id}/allocate", {
            params: {
              path: { payment_id: command.paymentId },
              header: { "Idempotency-Key": command.key },
            },
            body: command.body,
          });
          break;
        case "reverse":
          result = await client.POST("/api/v1/payments/{payment_id}/reverse", {
            params: { path: { payment_id: command.paymentId } },
            body: command.body,
          });
          break;
        case "task":
          result = await client.POST(
            "/api/v1/sales-orders/{order_id}/tasks/{task_id}/complete",
            {
              params: { path: { order_id: orderId, task_id: command.taskId } },
              body: command.body,
            },
          );
          break;
        case "complete":
          result = await client.POST(
            "/api/v1/sales-orders/{sales_order_id}/complete",
            { params: { path: orderPath }, body: command.body },
          );
          break;
      }
      if (!result.data)
        throw await parseApiError(result.response, result.error);
      return result.data;
    },
    onSuccess: async () => {
      await Promise.all([
        cache.invalidateQueries({ queryKey: ["order-finance"] }),
        cache.invalidateQueries({ queryKey: ["customer-payments"] }),
        cache.invalidateQueries({ queryKey: ["sales-order", orderId] }),
        cache.invalidateQueries({ queryKey: ["sales-orders"] }),
      ]);
    },
  });
}
