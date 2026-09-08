import { expect, test } from "@playwright/test";
import type { components } from "@trade-workbench/api-client";
import fs from "node:fs";
import path from "node:path";

test("manual queue refresh fetches page one despite fresh browser cache", async ({
  page,
}) => {
  const fixture = JSON.parse(
    fs.readFileSync(
      path.resolve(
        import.meta.dirname,
        "../../../test-results/e2e-fixture.json",
      ),
      "utf-8",
    ),
  );
  await page.addInitScript((session) => {
    localStorage.setItem(
      "trade-workbench.organization-id",
      session.organization_id,
    );
    localStorage.setItem("trade-workbench.access-token", session.access_token);
  }, fixture);
  let firstPageReads = 0;
  await page.route("**/api/v1/overview/leads?*", async (route) => {
    const later =
      new URL(route.request().url()).searchParams.get("offset") === "5";
    if (!later) firstPageReads += 1;
    const body: components["schemas"]["ActionPage"] = {
      queue: "leads",
      business_date: "2026-09-08",
      has_more: !later,
      next_offset: later ? null : 5,
      items: [
        {
          id: "00000000-0000-4000-8000-000000000001",
          title: later ? "浏览器第二页" : `浏览器第一页更新${firstPageReads}`,
          status: "NEW",
          due_date: null,
          overdue: false,
          href: "/leads/00000000-0000-4000-8000-000000000001",
          next_action: "跟进客户",
          missing_document_types: [],
        },
      ],
    };
    await route.fulfill({ json: body });
  });
  await page.goto("/");
  const queue = page.getByRole("region", { name: "待跟进线索" });
  await expect(queue.getByText("浏览器第一页更新1")).toBeVisible();
  await queue.getByRole("button", { name: "下一页" }).click();
  await expect(queue.getByText("浏览器第二页")).toBeVisible();
  await queue.getByRole("button", { name: "刷新" }).click();
  await expect(queue.getByText("浏览器第一页更新2")).toBeVisible();
  await expect(queue.getByText("浏览器第二页")).toHaveCount(0);
  await expect(queue.getByRole("button", { name: "上一页" })).toBeDisabled();
  await queue.getByRole("button", { name: "刷新" }).click();
  await expect(queue.getByText("浏览器第一页更新3")).toBeVisible();
});
