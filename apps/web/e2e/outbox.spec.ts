import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("manager inspects and manually requeues a failed event", async ({
  page,
}) => {
  const fixture = JSON.parse(
    fs.readFileSync(
      path.resolve(
        import.meta.dirname,
        "../../..",
        "test-results/e2e-fixture.json",
      ),
      "utf8",
    ),
  );
  await page.addInitScript((data) => {
    localStorage.setItem(
      "trade-workbench.organization-id",
      data.organization_id,
    );
    localStorage.setItem(
      "trade-workbench.access-token",
      data.manager_access_token,
    );
  }, fixture);
  await page.goto("/admin/outbox");
  await expect(page.getByText("fixture.acceptance_failure.v1")).toBeVisible();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/outbox-${width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "准备重放" }).click();
  await page.getByLabel("重放原因").fill("隔离验收：已核对后台服务和处理影响");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "确认重新排队" }).click();
  await expect(
    page.getByText(
      "事件已重新排队，尚不代表处理完成。请在相关业务对象核对结果。",
    ),
  ).toBeVisible();
  await expect(page.getByText("fixture.acceptance_failure.v1")).toHaveCount(0);
});
