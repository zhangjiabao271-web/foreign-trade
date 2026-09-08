import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

type Fixture = {
  organization_id: string;
  access_token: string;
  manager_access_token: string;
};

const fixturePath = path.resolve(
  import.meta.dirname,
  "../../..",
  "test-results/e2e-fixture.json",
);

function loadFixture(): Fixture {
  return JSON.parse(fs.readFileSync(fixturePath, "utf-8")) as Fixture;
}

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  const fixture = loadFixture();
  await page.addInitScript((session: Fixture) => {
    window.localStorage.setItem(
      "trade-workbench.organization-id",
      session.organization_id,
    );
    window.localStorage.setItem(
      "trade-workbench.access-token",
      session.access_token,
    );
  }, fixture);
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("creates and converts a lead through the complete browser path", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await page.goto("/leads");
  await expect(page.getByRole("heading", { name: "线索舱单" })).toBeVisible();
  await page.getByRole("button", { name: "登记新线索" }).first().click();
  await page.getByLabel("公司名称 *").fill("Aurora Components GmbH");
  await page.getByLabel("联系人").fill("Marta Klein");
  await page.getByLabel("邮箱").fill("marta@aurora.example");
  await page.getByLabel("国家代码").fill("DE");
  await page.getByLabel("来源").fill("Berlin trade fair");
  await page.getByRole("button", { name: "登记线索" }).click();

  await expect(page).toHaveURL(/\/leads\/[0-9a-f-]{36}$/);
  await expect(
    page.getByRole("heading", { name: "Aurora Components GmbH" }),
  ).toBeVisible();
  const detail = page.getByRole("region", {
    name: "Aurora Components GmbH",
  });
  await expect(detail.getByText("待判定", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "确认有效" }).click();
  await expect(detail.getByText("已确认", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "记录已联系" }).click();
  await expect(detail.getByText("已联系", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "记录客户回复" }).click();
  await expect(detail.getByText("已回复", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "转换为客户与商机" }).click();
  await expect(detail.getByText("转换凭证已建立")).toBeVisible();
  await expect(detail.getByText("已转换", { exact: true })).toBeVisible();

  await page.reload();
  await expect(detail.getByText("转换凭证已建立")).toBeVisible();
  await expect(detail.getByText("5 条记录")).toBeVisible();

  const manifest = page.getByRole("region", { name: "潜在客户", exact: true });
  const convertedLead = manifest.getByRole("link", {
    name: /Aurora Components GmbH/,
  });
  await page.getByLabel("搜索线索", { exact: true }).fill("aUrOrA");
  await expect(convertedLead).toHaveCount(1);
  await expect(manifest.getByText("1 条", { exact: true })).toBeVisible();
  await page.getByLabel("筛选状态", { exact: true }).selectOption("NEW");
  await expect(
    manifest.getByText("暂无匹配线索", { exact: true }),
  ).toBeVisible();
  await expect(convertedLead).toHaveCount(0);
  await page.getByLabel("筛选状态", { exact: true }).selectOption("CONVERTED");
  await expect(convertedLead).toHaveCount(1);
  await page.getByLabel("搜索线索", { exact: true }).fill("mArTa");
  await expect(convertedLead).toHaveCount(1);
  await expect(manifest.getByText("1 条", { exact: true })).toBeVisible();
  await page.getByLabel("搜索线索", { exact: true }).fill("absent-lead-search");
  await expect(
    manifest.getByText("暂无匹配线索", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("搜索线索", { exact: true }).fill("Aurora");
  await expect(convertedLead).toHaveCount(1);
  await expect(detail.getByText("5 条记录")).toBeVisible();

  await page.goto("/opportunities");
  await page.getByRole("link", { name: /Aurora Components GmbH/ }).click();
  await expect(page.getByText("当前阶段 · 待询盘")).toBeVisible();
  await page.getByRole("button", { name: "标记丢单" }).click();
  await page.getByLabel("处理原因").fill("客户项目延期，保留资料等待新的线索");
  await page.getByRole("checkbox").check();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: `test-results/opportunity-loss-${width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "确认丢单" }).click();
  await expect(page.getByText("当前阶段 · 已丢单")).toBeVisible();
  const source = page.getByRole("region", { name: "丢单原因审核" });
  await expect(source.getByText(/保密/)).toBeVisible();
  await expect(source.getByText(/客户项目延期/)).toHaveCount(0);
  const fixture = loadFixture();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  await source
    .getByRole("button", { name: "审核文本开放范围", exact: true })
    .click();
  await source.getByLabel("审核决定").selectOption("release");
  await source
    .getByLabel("审核说明")
    .fill("已核对丢单原因全文，不含内部成本和利润");
  await source.getByRole("checkbox").check();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await source.screenshot({
      path: `test-results/crm-source-review-${width}.png`,
    });
  }
  await source.getByRole("button", { name: "确认文本审核" }).click();
  await expect(
    source.getByText("本条文本已开放。", { exact: true }),
  ).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.access_token);
  await expect(
    source.getByText(/客户项目延期，保留资料等待新的线索/),
  ).toBeVisible();
  await expect(
    source.getByRole("button", { name: "审核文本开放范围" }),
  ).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("当前阶段 · 已丢单")).toBeVisible();
  await expect(page.getByRole("button", { name: "标记丢单" })).toHaveCount(0);
});

test("skip link is keyboard reachable and reveals the main target", async ({
  page,
}) => {
  await page.goto("/copilot");
  await expect(
    page.getByRole("heading", { name: "受控业务助手" }),
  ).toBeVisible();
  const skip = page.getByRole("link", { name: "跳到主要内容" });
  await expect(skip).toHaveCSS("clip-path", "inset(50%)");
  await page.keyboard.press("Tab");
  await expect(skip).toBeFocused();
  await expect(skip).toHaveCSS("clip-path", "none");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main-content$/);
  await expect(page.locator("#main-content")).toBeInViewport();
});

for (const viewport of [
  { width: 375, height: 812 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
]) {
  test(`has no horizontal overflow at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("/leads");
    await expect(page.getByRole("heading", { name: "线索舱单" })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
    await page.screenshot({
      path: `test-results/leads-${viewport.width}.png`,
      fullPage: true,
    });
  });
}
