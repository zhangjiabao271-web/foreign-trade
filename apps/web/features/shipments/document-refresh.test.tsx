import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { useShipment, useShipmentDocuments } from "./api";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it.each(["AVAILABLE", "REJECTED"])(
  "refreshes the server checklist when document polling reaches %s",
  async (terminalStatus) => {
    let processed = false;
    let shipmentReads = 0;
    const missing = ["COMMERCIAL_INVOICE"];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const body = request.url.includes("/documents?")
        ? {
            count: 1,
            items: [
              {
                id: "document-1",
                versions: [{ status: processed ? terminalStatus : "SCANNING" }],
              },
            ],
          }
        : {
            id: "shipment-1",
            version: ++shipmentReads,
            missing_required_documents:
              processed && terminalStatus === "AVAILABLE" ? [] : missing,
          };
      return new Response(JSON.stringify(body), {
        headers: { "content-type": "application/json" },
      });
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { result, unmount } = renderHook(
      () => ({
        shipment: useShipment("shipment-1", true),
        documents: useShipmentDocuments("shipment-1", true),
      }),
      {
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );
    await waitFor(() =>
      expect(
        result.current.documents.data?.items[0]?.versions?.[0]?.status,
      ).toBe("SCANNING"),
    );
    await waitFor(() => expect(result.current.shipment.isFetching).toBe(false));
    const readsBeforeScan = shipmentReads;
    processed = true;
    await waitFor(
      () =>
        expect(
          result.current.documents.data?.items[0]?.versions?.[0]?.status,
        ).toBe(terminalStatus),
      { timeout: 4000 },
    );
    await waitFor(() => expect(shipmentReads).toBeGreaterThan(readsBeforeScan));
    await waitFor(() =>
      expect(result.current.shipment.data?.missing_required_documents).toEqual(
        terminalStatus === "AVAILABLE" ? [] : missing,
      ),
    );
    unmount();
    client.clear();
  },
);
