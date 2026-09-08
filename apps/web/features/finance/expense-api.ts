"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { parseApiError, type components } from "@trade-workbench/api-client";
import { sessionClient } from "../overview/session";

type Schema = components["schemas"];
export type Expense = Schema["ExpenseResponse"];
export type ExpenseWrite =
  | { action: "record"; body: Schema["ExpenseCreate"]; key: string }
  | {
      action: "reverse";
      id: string;
      body: Schema["ExpenseReverse"];
      key: string;
    };

export function useExpenses(scope: string, orderId: string, cursor?: string) {
  return useQuery({
    queryKey: ["expenses", scope, orderId, cursor],
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET(
        "/api/v1/sales-orders/{order_id}/expenses",
        {
          params: { path: { order_id: orderId }, query: { cursor, limit: 20 } },
        },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useExpenseSummary(
  scope: string,
  orderId: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["expense-summary", scope, orderId],
    enabled,
    retry: false,
    queryFn: async () => {
      const r = await sessionClient().GET(
        "/api/v1/sales-orders/{order_id}/expenses/summary",
        {
          params: { path: { order_id: orderId } },
        },
      );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
  });
}
export function useExpenseWrite(scope: string, orderId: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: async (command: ExpenseWrite) => {
      const client = sessionClient();
      const params = {
        path: {
          order_id: orderId,
          expense_id: command.action === "reverse" ? command.id : "",
        },
        header: { "Idempotency-Key": command.key },
      };
      const r =
        command.action === "record"
          ? await client.POST("/api/v1/sales-orders/{order_id}/expenses", {
              params,
              body: command.body,
            })
          : await client.POST(
              "/api/v1/sales-orders/{order_id}/expenses/{expense_id}/reverse",
              { params, body: command.body },
            );
      if (!r.data) throw await parseApiError(r.response, r.error);
      return r.data;
    },
    onSuccess: async () => {
      await Promise.all([
        cache.invalidateQueries({ queryKey: ["expenses", scope, orderId] }),
        cache.invalidateQueries({
          queryKey: ["funding-estimate", scope, orderId],
        }),
        cache.invalidateQueries({
          queryKey: ["expense-summary", scope, orderId],
        }),
        cache.invalidateQueries({ queryKey: ["order-finance"] }),
      ]);
    },
  });
}
