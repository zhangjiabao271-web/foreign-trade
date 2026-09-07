import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("administrator reads tenant operational evidence and window limits", async ({
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
  ) as { organization_id: string; admin_access_token: string };
  await page.addInitScript((session) => {
    localStorage.setItem(
      "trade-workbench.organization-id",
      session.organization_id,
    );
    localStorage.setItem(
      "trade-workbench.access-token",
      session.admin_access_token,
    );
  }, fixture);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/admin/operations");
  await expect(
    page.getByRole("heading", { name: "先处理未完成的投递" }),
  ).toBeVisible();
  await expect(page.getByText("暂无已决请求")).toBeVisible();
  await expect(
    page.getByText("仅当前 API 进程的有界内存窗口", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "刷新运行数据" }).click();
  await expect(
    page.getByRole("button", { name: "刷新运行数据" }),
  ).toBeEnabled();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/operations-${width}.png`,
      fullPage: true,
    });
  }
});
