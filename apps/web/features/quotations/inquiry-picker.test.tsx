import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { InquiryPicker } from "./inquiry-picker";
import { sessionKeys } from "../leads/api";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

it("selects an older inquiry without exposing source prose", async () => {
  localStorage.setItem(
    sessionKeys.organizationId,
    "00000000-0000-4000-8000-000000000001",
  );
  localStorage.setItem(sessionKeys.accessToken, "test-member");
  const onSelect = vi.fn();
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const request = input instanceof Request ? input : new Request(input);
    const url = new URL(request.url);
    const cursor = url.searchParams.get("cursor");
    const body = url.pathname.endsWith("/me/context")
      ? { permissions: ["inquiry.read"] }
      : {
          items: [
            {
              id: cursor ? "older" : "newer",
              customer_reference: cursor ? "RFQ-OLD" : "RFQ-NEW",
              received_at: "2026-09-01T00:00:00Z",
              description: "DO-NOT-SHOW",
            },
          ],
          count: 1,
          has_more: !cursor,
          next_cursor: cursor ? null : "newer",
        };
    return new Response(JSON.stringify(body), {
      headers: { "content-type": "application/json" },
    });
  });
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <InquiryPicker disabled={false} onSelect={onSelect} />
    </QueryClientProvider>,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "从已有询盘选择" }),
  );
  fireEvent.click(await screen.findByRole("button", { name: "加载更多询盘" }));
  fireEvent.click(await screen.findByRole("button", { name: "选择 RFQ-OLD" }));
  expect(onSelect).toHaveBeenCalledWith("older");
  expect(screen.queryByText("DO-NOT-SHOW")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "从已有询盘选择" }),
  ).toHaveAttribute("aria-expanded", "false");
});
