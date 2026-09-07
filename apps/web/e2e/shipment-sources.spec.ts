import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("shipment detail resolves old sources directly with confidential text and explicit retry", async ({
  page,
}) => {
  const fixture = JSON.parse(
    fs.readFileSync(
      path.resolve(
        import.meta.dirname,
        "../../../test-results/e2e-fixture.json",
      ),
      "utf8",
    ),
  );
  await page.addInitScript((session) => {
    localStorage.setItem(
      "trade-workbench.organization-id",
      session.organization_id,
    );
    localStorage.setItem(
      "trade-workbench.access-token",
      session.operations_access_token,
    );
  }, fixture);
  const id = "00000000-0000-4000-8000-000000007001";
  const lineId = "00000000-0000-4000-8000-000000007002";
  const shipment = {
    id,
    version: 1,
    shipment_number: "SHP-DIRECT-SOURCE",
    status: "PLANNING",
    booking_reference: null,
    planned_departure_date: null,
    planned_arrival_date: null,
    created_at: "2000-01-01T00:00:00Z",
    missing_required_documents: ["COMMERCIAL_INVOICE", "PACKING_LIST"],
    items: [
      {
        id: "00000000-0000-4000-8000-000000007003",
        sales_order_item_id: lineId,
        quantity: "1.0000",
      },
    ],
  };
  let unavailable = true;
  let orderPageRequests = 0;
  await page.route("**/api/backend/api/v1/documents?**", (route) =>
    route.fulfill({ json: { items: [], count: 0 } }),
  );
  await page.route("**/api/backend/api/v1/sales-orders?**", async (route) => {
    orderPageRequests++;
    await route.fulfill({
      json: { items: [], count: 0, has_more: false, next_cursor: null },
    });
  });
  await page.route("**/api/backend/api/v1/shipments**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/source-lines")) {
      if (unavailable)
        return route.fulfill({
          status: 503,
          json: { detail: "Unavailable source" },
        });
      return route.fulfill({
        json: {
          count: 1,
          items: [
            {
              id: lineId,
              sales_order_id: "00000000-0000-4000-8000-000000007004",
              order_number: "SO-OLD-DIRECT",
              order_status: "COMPLETED",
              sku_snapshot: "OLD-SOURCE-SKU",
              description_snapshot: null,
              unit_snapshot: "set",
            },
          ],
        },
      });
    }
    return route.fulfill({
      json: url.pathname.endsWith(id)
        ? shipment
        : { items: [shipment], count: 1, has_more: false, next_cursor: null },
    });
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/shipments/${id}`);
  const retry = page.getByRole("button", { name: "重试来源快照" });
  await expect(retry).toBeVisible();
  await expect(page.getByText("来源快照暂不可用")).toBeVisible();
  unavailable = false;
  await retry.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("SO-OLD-DIRECT", { exact: true })).toBeVisible();
  await expect(page.getByText("订单原文未获审核开放")).toBeVisible();
  await expect(
    page.getByText("关联订单已终结，不能记录新的出运节点。"),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "记录已订舱" })).toHaveCount(0);
  expect(orderPageRequests).toBe(0);
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 950 });
    await page
      .getByText("SO-OLD-DIRECT", { exact: true })
      .scrollIntoViewIfNeeded();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await page.screenshot({
      path: `test-results/shipment-direct-source-${width}.png`,
      fullPage: true,
    });
  }
});
