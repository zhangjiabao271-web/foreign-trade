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
import { collectCursorItems } from "../../lib/cursor-pages";
import { useRef } from "react";

import { sessionKeys } from "../leads/api";
import { useSessionScope } from "../overview/session";

export type Quotation = components["schemas"]["QuotationResponse"];
export type QuotationListItem = components["schemas"]["QuotationListItem"];
export type QuotationCreate = components["schemas"]["QuotationCreate"];
export type QuotationRevisionCreate =
  components["schemas"]["QuotationRevisionCreate"];
export type QuotationVersion =
  components["schemas"]["QuotationVersionResponse"];
export type QuotationStatus = components["schemas"]["QuotationVersionStatus"];
export type ProductCreate = components["schemas"]["ProductCreate"];
export type InquiryCreate = components["schemas"]["InquiryCreate"];

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

export function useQuotations(status: "" | QuotationStatus, enabled: boolean) {
  const scope = useSessionScope();
  const queryClient = useQueryClient();
  const queryKey = ["quotations", scope, status, "pages"];
  const query = useInfiniteQuery({
    queryKey,
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const { data, error, response } = await tradeApi().GET(
        "/api/v1/quotations",
        {
          params: {
            query: {
              status: status || undefined,
              limit: 50,
              cursor: pageParam,
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

export function useQuotation(id: string | undefined, enabled: boolean) {
  const scope = useSessionScope();
  return useQuery({
    queryKey: ["quotation", scope, id],
    enabled: enabled && Boolean(id),
    queryFn: async () => {
      const { data, error, response } = await tradeApi().GET(
        "/api/v1/quotations/{quotation_id}",
        { params: { path: { quotation_id: id! } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
  });
}

export function useInquiries(enabled: boolean) {
  const scope = useSessionScope();
  const queryClient = useQueryClient();
  const queryKey = ["inquiries", scope, "OPEN", "pages"];
  const query = useInfiniteQuery({
    queryKey,
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const { data, error, response } = await tradeApi().GET(
        "/api/v1/inquiries",
        {
          params: { query: { status: "OPEN", limit: 50, cursor: pageParam } },
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

function useRefreshQuotation(id?: string) {
  const scope = useSessionScope();
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["quotations"] }),
      queryClient.invalidateQueries({ queryKey: ["inquiries"] }),
      id
        ? queryClient.invalidateQueries({ queryKey: ["quotation", scope, id] })
        : Promise.resolve(),
    ]);
  };
}

export function useCreateQuotation() {
  const refresh = useRefreshQuotation();
  return useMutation({
    mutationFn: async ({
      body,
      key,
    }: {
      body: QuotationCreate;
      key: string;
    }) => {
      const { data, error, response } = await tradeApi().POST(
        "/api/v1/quotations",
        { body, params: { header: { "Idempotency-Key": key } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    onSuccess: refresh,
  });
}

export function useReviseQuotation(id: string) {
  const refresh = useRefreshQuotation(id);
  return useMutation({
    mutationFn: async ({
      body,
      key,
    }: {
      body: QuotationRevisionCreate;
      key: string;
    }) => {
      const { data, error, response } = await tradeApi().POST(
        "/api/v1/quotations/{quotation_id}/revisions",
        {
          params: {
            path: { quotation_id: id },
            header: { "Idempotency-Key": key },
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

export type QuotationCommand =
  "submit" | "approve" | "send" | "accept" | "reject" | "expire";

export function useQuotationCommand(id: string) {
  const refresh = useRefreshQuotation(id);
  const retry = useRef<{ payload: string; key: string } | null>(null);
  return useMutation({
    mutationFn: async ({
      command,
      body,
    }: {
      command: QuotationCommand;
      body: components["schemas"]["QuotationStateCommand"];
    }) => {
      const payload = JSON.stringify({ id, command, body });
      if (retry.current?.payload !== payload) {
        retry.current = { payload, key: crypto.randomUUID() };
      }
      const header = { "Idempotency-Key": retry.current.key };
      if (command === "accept" || command === "reject") {
        const { data, error, response } = await tradeApi().POST(
          "/api/v1/quotations/{quotation_id}/{command}",
          { body, params: { path: { quotation_id: id, command }, header } },
        );
        if (!data) throw await parseApiError(response, error);
        return data;
      }
      const path = `/api/v1/quotations/{quotation_id}/${command}` as
        | "/api/v1/quotations/{quotation_id}/submit"
        | "/api/v1/quotations/{quotation_id}/approve"
        | "/api/v1/quotations/{quotation_id}/send"
        | "/api/v1/quotations/{quotation_id}/expire";
      const { data, error, response } = await tradeApi().POST(path, {
        body,
        params: { path: { quotation_id: id }, header },
      });
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    onSuccess: refresh,
  });
}

export function useCreateProduct() {
  return useMutation({
    mutationFn: async (body: ProductCreate) => {
      const { data, error, response } = await tradeApi().POST(
        "/api/v1/products",
        { body },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
  });
}

export function useCustomerReview(id: string) {
  const refresh = useRefreshQuotation(id);
  return useMutation({
    mutationFn: async ({
      body,
      key,
    }: {
      body: components["schemas"]["CustomerReviewCommand"];
      key: string;
    }) => {
      const { data, error, response } = await tradeApi().POST(
        "/api/v1/quotations/{quotation_id}/mark-customer-review",
        {
          params: {
            path: { quotation_id: id },
            header: { "Idempotency-Key": key },
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

export function useCreateInquiry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ body, key }: { body: InquiryCreate; key: string }) => {
      const { data, error, response } = await tradeApi().POST(
        "/api/v1/inquiries",
        { body, params: { header: { "Idempotency-Key": key } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["inquiries"] }),
  });
}
