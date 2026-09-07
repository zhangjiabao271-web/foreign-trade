import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("commercial queues retain filters, load older inquiries and clear pages on role switch", async ({
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
      session.manager_access_token,
    );
  }, fixture);
  const ids = Array.from(
    { length: 51 },
    (_, index) =>
      `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
  );
  await page.route(
    /\/api\/backend\/api\/v1\/(quotations|inquiries|shipments)\?/,
    async (route) => {
      const url = new URL(route.request().url());
      const kind = url.pathname.split("/").at(-1);
      const cursor = url.searchParams.get("cursor");
      if (cursor) expect(cursor).toBe(ids[49]);
      if (kind === "inquiries")
        expect(url.searchParams.get("status")).toBe("OPEN");
      const items = ids.map((id, index) => ({
        id,
        quotation_number: `QT-PAGE-${index}`,
        shipment_number: `SHP-PAGE-${index}`,
        customer_reference: `RFQ-PAGE-${index}`,
        received_at: "2026-09-01T00:00:00Z",
        description: null,
        version_number: 1,
        currency_code: "USD",
        total: "100.0000",
        valid_until: "2026-12-31",
        status:
          kind === "shipments"
            ? "PLANNING"
            : url.searchParams.get("status") || "DRAFT",
        planned_departure_date: null,
        planned_arrival_date: null,
        items: [],
      }));
      await route.fulfill({
        json: {
          items: cursor ? items.slice(50) : items.slice(0, 50),
          count: cursor ? 1 : 50,
          has_more: !cursor,
          next_cursor: cursor ? null : ids[49],
        },
      });
    },
  );
  await page.goto("/quotations");
  await page.getByRole("button", { name: "加载更多报价" }).click();
  await expect(page.locator(".quote-row")).toHaveCount(51);
  await page.getByLabel("筛选报价状态").selectOption("SENT");
  await expect(page.locator(".quote-row")).toHaveCount(50);
  await expect(page.locator(".quote-row .status-chip").first()).toHaveText(
    "已发送",
  );
  await page.getByRole("button", { name: "创建报价 V1", exact: true }).click();
  await page.getByRole("button", { name: "从已有询盘选择" }).click();
  await page.getByRole("button", { name: "加载更多询盘" }).click();
  const older = page.getByRole("button", {
    name: "选择 RFQ-PAGE-50",
    exact: true,
  });
  await older.scrollIntoViewIfNeeded();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 950 });
    await older.scrollIntoViewIfNeeded();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await page.screenshot({ path: `test-results/inquiry-page-${width}.png` });
  }
  await older.click();
  await expect(page.getByLabel("询盘 ID *", { exact: true })).toHaveValue(
    ids[50],
  );
  await page.goto("/shipments");
  await page.getByRole("button", { name: "加载更多出运单" }).click();
  await expect(page.locator(".shipment-row")).toHaveCount(51);
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.operations_access_token);
  await expect(page.locator(".shipment-row")).toHaveCount(50);
  await expect(
    page.getByRole("button", { name: "加载更多出运单" }),
  ).toBeVisible();
});
