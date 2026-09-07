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
import { useEffect, useRef } from "react";

import { sessionKeys } from "../leads/api";
import { uploadDocument } from "../documents/transfer";
import { useUploadRetry } from "../documents/use-upload-retry";
import { sessionClient } from "../overview/session";

export type Shipment = components["schemas"]["ShipmentResponse"];
export type ShipmentCreate = components["schemas"]["ShipmentCreate"];
export type DocumentRecord = components["schemas"]["DocumentResponse"];

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

export function useShipments(enabled: boolean) {
  const queryClient = useQueryClient();
  const queryKey = ["shipments", "pages"];
  const query = useInfiniteQuery({
    queryKey,
    enabled,
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const { data, error, response } = await tradeApi().GET(
        "/api/v1/shipments",
        { params: { query: { limit: 50, cursor: pageParam } } },
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

export function useShipment(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["shipment", id],
    enabled: enabled && Boolean(id),
    queryFn: async () => {
      const { data, error, response } = await tradeApi().GET(
        "/api/v1/shipments/{shipment_id}",
        { params: { path: { shipment_id: id! } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
  });
}

export function useShipmentSources(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["sales-orders", "shipment-sources", id],
    enabled: enabled && Boolean(id),
    queryFn: async () => {
      const { data, error, response } = await tradeApi().GET(
        "/api/v1/shipments/{shipment_id}/source-lines",
        { params: { path: { shipment_id: id! } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
  });
}

export function useShipmentDocuments(id: string | undefined, enabled: boolean) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["shipment-documents", id],
    enabled: enabled && Boolean(id),
    refetchInterval: (query) =>
      query.state.data?.items.some((document) =>
        (document.versions ?? []).some((version) =>
          ["PENDING_UPLOAD", "UPLOADED", "SCANNING"].includes(version.status),
        ),
      )
        ? 2000
        : false,
    queryFn: async () => {
      const { data, error, response } = await tradeApi().GET(
        "/api/v1/documents",
        { params: { query: { target_type: "SHIPMENT", target_id: id! } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
  });
  useEffect(() => {
    if (!enabled || !id || !query.data) return;
    // Scanning finishes after upload mutation invalidation. Re-read the server
    // checklist when document facts change; never derive business readiness here.
    void queryClient.invalidateQueries({ queryKey: ["shipment", id] });
  }, [enabled, id, query.data, queryClient]);
  return query;
}

export function useRefreshShipment(id?: string) {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["shipments"] }),
      id
        ? queryClient.invalidateQueries({ queryKey: ["shipment", id] })
        : Promise.resolve(),
      id
        ? queryClient.invalidateQueries({
            queryKey: ["shipment-documents", id],
          })
        : Promise.resolve(),
      queryClient.invalidateQueries({ queryKey: ["sales-orders"] }),
    ]);
  };
}

export function useCreateShipment() {
  const refresh = useRefreshShipment();
  return useMutation({
    mutationFn: async ({
      body,
      key,
    }: {
      body: ShipmentCreate;
      key: string;
    }) => {
      const { data, error, response } = await tradeApi().POST(
        "/api/v1/shipments",
        { body, params: { header: { "idempotency-key": key } } },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    onSuccess: refresh,
  });
}

type ShipmentCommand =
  "ready" | "enter-customs" | "depart" | "start-transit" | "arrive" | "deliver";

export function useShipmentCommand(id: string) {
  const refresh = useRefreshShipment(id);
  const attempt = useRef<{ fingerprint: string; key: string } | null>(null);
  return useMutation({
    mutationFn: async (
      input:
        | { command: "book"; body: components["schemas"]["ShipmentBook"] }
        | {
            command: ShipmentCommand;
            body: components["schemas"]["ShipmentDecision"];
          },
    ) => {
      const fingerprint = JSON.stringify({ id, input });
      if (attempt.current?.fingerprint !== fingerprint) {
        attempt.current = { fingerprint, key: crypto.randomUUID() };
      }
      const params = {
        path: { shipment_id: id },
        header: { "idempotency-key": attempt.current.key },
      };
      if (input.command === "book") {
        const { data, error, response } = await tradeApi().POST(
          "/api/v1/shipments/{shipment_id}/book",
          {
            params,
            body: input.body,
          },
        );
        if (!data) throw await parseApiError(response, error);
        return data;
      }
      const paths = {
        ready: "/api/v1/shipments/{shipment_id}/ready",
        "enter-customs": "/api/v1/shipments/{shipment_id}/enter-customs",
        depart: "/api/v1/shipments/{shipment_id}/depart",
        "start-transit": "/api/v1/shipments/{shipment_id}/start-transit",
        arrive: "/api/v1/shipments/{shipment_id}/arrive",
        deliver: "/api/v1/shipments/{shipment_id}/deliver",
      } as const;
      const { data, error, response } = await tradeApi().POST(
        paths[input.command],
        { params, body: input.body },
      );
      if (!data) throw await parseApiError(response, error);
      return data;
    },
    onSuccess: refresh,
  });
}

export function useUploadShipmentDocument(shipmentId: string) {
  const refresh = useRefreshShipment(shipmentId);
  const retry = useUploadRetry();
  return useMutation({
    mutationFn: async (input: {
      file: File;
      documentType: string;
      replacement?: { documentId: string; expectedVersion: number };
    }) => {
      return uploadDocument(
        sessionClient(),
        {
          file: input.file,
          documentType:
            input.documentType as components["schemas"]["DocumentType"],
          targetType: "SHIPMENT",
          targetId: shipmentId,
          replacement: input.replacement,
        },
        retry(),
      );
    },
    onSuccess: refresh,
  });
}

export function useDownloadShipmentDocument() {
  return useMutation({
    mutationFn: async ({
      documentId,
      versionId,
    }: {
      documentId: string;
      versionId?: string;
    }) => {
      const result = versionId
        ? await tradeApi().POST(
            "/api/v1/documents/{document_id}/versions/{version_id}/download-session",
            {
              params: {
                path: { document_id: documentId, version_id: versionId },
              },
            },
          )
        : await tradeApi().POST(
            "/api/v1/documents/{document_id}/download-session",
            { params: { path: { document_id: documentId } } },
          );
      const { data, error, response } = result;
      if (!data) throw await parseApiError(response, error);
      return data;
    },
  });
}
