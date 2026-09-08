import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("order pages recover and expose older shipment sources within the session", async ({
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
  const orders = Array.from({ length: 51 }, (_, index) => ({
    id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    order_number: `SO-PAGE-${String(index + 1).padStart(3, "0")}`,
    status: index === 50 ? "EXECUTING" : "COMPLETED",
    currency_code: "USD",
    total: "100.0000",
    deposit_due_date: null,
    items:
      index === 50
        ? [
            {
              id: "00000000-0000-4000-8000-000000000999",
              sku_snapshot: "OLDER-SOURCE",
              description_snapshot: null,
              unit_snapshot: "set",
              quantity: "2.0000",
            },
          ]
        : [],
  }));
  let failNext = true;
  await page.route("**/api/backend/api/v1/sales-orders?**", async (route) => {
    const cursor = new URL(route.request().url()).searchParams.get("cursor");
    if (cursor && failNext) {
      await route.abort("failed");
      return;
    }
    if (cursor) expect(cursor).toBe(orders[49].id);
    await route.fulfill({
      json: {
        items: cursor ? orders.slice(50) : orders.slice(0, 50),
        count: cursor ? 1 : 50,
        has_more: !cursor,
        next_cursor: cursor ? null : orders[49].id,
      },
    });
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/orders");
  await expect(page.getByText("已加载 50 份")).toBeVisible();
  const more = page.getByRole("button", { name: "加载更多订单" });
  await expect(more).toHaveAttribute("data-slot", "button");
  await more.focus();
  await expect(more).toBeFocused();
  const buttonStyle = await more.evaluate((element) => ({
    height: element.getBoundingClientRect().height,
    outline: getComputedStyle(element).outlineStyle,
  }));
  expect(buttonStyle.height).toBeGreaterThanOrEqual(44);
  expect(buttonStyle.outline).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(page.getByText(/订单分页加载失败/)).toBeVisible();
  await expect(page.locator(".order-row")).toHaveCount(50);
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 950 });
    await page
      .getByRole("button", { name: "重新加载订单清单" })
      .scrollIntoViewIfNeeded();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await page.screenshot({
      path: `test-results/order-page-retry-${width}.png`,
    });
  }
  failNext = false;
  await more.click();
  await expect(page.getByText("已加载 51 份")).toBeVisible();
  await expect(page.locator(".order-row")).toHaveCount(51);
  await expect(more).toHaveCount(0);
  await page.goto("/shipments");
  await page.getByRole("button", { name: "创建出运计划", exact: true }).click();
  await expect(page.getByText(/已加载记录中没有可出运订单/)).toBeVisible();
  await page.getByRole("button", { name: "加载更多订单" }).click();
  await expect(page.getByText("SO-PAGE-051", { exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: "OLDER-SOURCE" }).check();
  await page.getByLabel("OLDER-SOURCE 本次出运数量").fill("0.5000");
  await expect(page.getByLabel("OLDER-SOURCE 本次出运数量")).toHaveValue(
    "0.5000",
  );
  // UI fixture verifies navigation only; real PostgreSQL/capacity acceptance lives in pytest.
});
