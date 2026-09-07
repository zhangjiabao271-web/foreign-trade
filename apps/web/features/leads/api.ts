"use client";

import {
  createTradeApiClient,
  parseApiError,
  type components,
} from "@trade-workbench/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

export type Lead = components["schemas"]["LeadResponse"];
export type LeadDetail = components["schemas"]["LeadDetailResponse"];
export type LeadCreate = components["schemas"]["LeadCreate"];
export type LeadStatus = components["schemas"]["LeadStatus"];

export const sessionKeys = {
  organizationId: "trade-workbench.organization-id",
  accessToken: "trade-workbench.access-token",
  marker: "trade-workbench.session-marker",
} as const;

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

export function useLeads(
  filters: { status?: LeadStatus; query?: string },
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["leads", filters],
    enabled,
    queryFn: async () => {
      const { data, error, response } = await tradeApi().GET("/api/v1/leads", {
        params: { query: { ...filters, limit: 50 } },
      });
      if (!data) throw await parseApiError(response, error);
      return data;
    },
  });
}

export function useLead(leadId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["lead", leadId],
    enabled: enabled && Boolean(leadId),
    queryFn: async () => {
      const { data, error, response } = await tradeApi().GET(
        "/api/v1/leads/{lead_id}",
        { params: { path: { lead_id: leadId! } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
  });
}

export function useCreateLead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: LeadCreate) => {
      const { data, error, response } = await tradeApi().POST("/api/v1/leads", {
        body,
      });
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    onSuccess: async () =>
      queryClient.invalidateQueries({ queryKey: ["leads"] }),
  });
}

export type LeadCommand =
  "qualify" | "contact" | "respond" | "no-response" | "disqualify";

export function useLeadCommand(leadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (command: LeadCommand) => {
      const { data, error, response } = await tradeApi().POST(
        "/api/v1/leads/{lead_id}/{command}",
        { params: { path: { lead_id: leadId, command } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["leads"] }),
        queryClient.invalidateQueries({ queryKey: ["lead", leadId] }),
      ]);
    },
  });
}

export function useConvertLead(leadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data, error, response } = await tradeApi().POST(
        "/api/v1/leads/{lead_id}/convert",
        { params: { path: { lead_id: leadId } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["leads"] }),
        queryClient.invalidateQueries({ queryKey: ["lead", leadId] }),
      ]);
    },
  });
}
