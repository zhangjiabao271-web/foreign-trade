import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { useShipments } from "../shipments/api";
import { useInquiries, useQuotations } from "../quotations/api";
import { usePurchaseOrders } from "./api";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

function wrapper({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: { queries: { retry: false } },
        })
      }
    >
      {children}
    </QueryClientProvider>
  );
}

it.each([
  { path: "shipments", useList: () => useShipments(true), filters: {} },
  {
    path: "purchase-orders",
    useList: () => usePurchaseOrders(true, "parent-order"),
    filters: { sales_order_id: "parent-order" },
  },
  {
    path: "quotations",
    useList: () => useQuotations("SENT", true),
    filters: { status: "SENT" },
  },
  {
    path: "inquiries",
    useList: () => useInquiries(true),
    filters: { status: "OPEN" },
  },
])(
  "$path preserves filters, loaded rows and exact cursor retry",
  async ({ path, useList, filters }) => {
    const cursors: (string | null)[] = [];
    let fail = true;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const url = new URL(request.url);
      expect(url.pathname.endsWith(`/${path}`)).toBe(true);
      for (const [key, value] of Object.entries(filters))
        expect(url.searchParams.get(key)).toBe(value);
      const cursor = url.searchParams.get("cursor");
      cursors.push(cursor);
      if (cursor && fail) throw new TypeError("Synthetic paging failure");
      return new Response(
        JSON.stringify({
          items: cursor ? [{ id: "older" }] : [{ id: "newer" }],
          count: 1,
          has_more: !cursor,
          next_cursor: cursor ? null : "newer",
        }),
        { headers: { "content-type": "application/json" } },
      );
    });
    const { result } = renderHook<ReturnType<typeof useList>, unknown>(
      useList,
      { wrapper },
    );
    await waitFor(() => expect(result.current.data?.count).toBe(1));
    await act(async () => {
      await result.current.fetchNextPage();
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data?.items.map((item) => item.id)).toEqual([
      "newer",
    ]);
    fail = false;
    await act(async () => {
      await result.current.fetchNextPage();
    });
    await waitFor(() =>
      expect(result.current.data?.items.map((item) => item.id)).toEqual([
        "newer",
        "older",
      ]),
    );
    expect(result.current.hasNextPage).toBe(false);
    expect(cursors).toEqual([null, "newer", "newer"]);
    await act(async () => {
      await result.current.restart();
    });
    await waitFor(() => expect(result.current.data?.count).toBe(1));
    expect(cursors.at(-1)).toBeNull();
  },
);
