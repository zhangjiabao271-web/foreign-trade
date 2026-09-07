import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

type Fixture = {
  organization_id: string;
  access_token: string;
  manager_access_token: string;
  operations_access_token: string;
};
test("maintains a unified company and contact archive with responsive forms", async ({
  page,
}) => {
  test.setTimeout(120_000);
  const fixture = JSON.parse(
    fs.readFileSync(
      path.resolve(
        import.meta.dirname,
        "../../../test-results/e2e-fixture.json",
      ),
      "utf8",
    ),
  ) as Fixture;
  await page.addInitScript((session: Fixture) => {
    localStorage.setItem(
      "trade-workbench.organization-id",
      session.organization_id,
    );
    localStorage.setItem("trade-workbench.access-token", session.access_token);
  }, fixture);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/companies");
  await page.getByRole("button", { name: "新建公司", exact: true }).click();
  await page
    .getByLabel("公司名称", { exact: true })
    .fill("Harbor Unified Trading");
  await page.getByLabel("国家代码（选填）").fill("CN");
  await page.getByLabel("公司网站（选填）").fill("https://harbor.example");
  await page.getByLabel("客户", { exact: true }).check();
  await page.getByLabel("供应商", { exact: true }).check();
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
      path: `test-results/company-create-${width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "保存档案" }).click();
  await expect(page).toHaveURL(/\/companies\/[0-9a-f-]{36}$/);
  await expect(
    page.getByRole("heading", { name: "Harbor Unified Trading" }),
  ).toBeVisible();
  await expect(page.getByText("客户 · 供应商", { exact: true })).toBeVisible();
  await page.getByLabel("增加业务角色").selectOption("FORWARDER");
  await page.getByRole("button", { name: "确认增加角色" }).click();
  await expect(page.getByText("业务角色已增加。")).toBeVisible();
  await page.getByRole("button", { name: "编辑公司资料", exact: true }).click();
  await page
    .getByLabel("公司名称", { exact: true })
    .fill("Harbor Unified Trading Ltd");
  await page.getByLabel("修改原因").fill("核对公司注册名称");
  await page.getByRole("button", { name: "保存档案" }).click();
  await expect(page.getByText("公司资料已保存。")).toBeVisible();
  await page.getByRole("button", { name: "新建联系人", exact: true }).click();
  await page.getByLabel("联系人姓名").fill("林女士");
  await page.getByLabel("邮箱（选填）").fill("lin@harbor.example");
  await page.getByLabel("职务（选填）").fill("采购经理");
  await page.getByRole("button", { name: "保存档案" }).click();
  await expect(page.getByText("联系人已保存。")).toBeVisible();
  await page.getByRole("button", { name: "编辑联系人 林女士" }).click();
  await page.getByLabel("电话（选填）").fill("+86 21 5555 0101");
  await page.getByLabel("修改原因").fill("联系人确认电话号码");
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
      path: `test-results/company-contact-${width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "保存档案" }).click();
  await expect(page.getByText("联系人已保存。")).toBeVisible();
  await page.reload();
  await expect(
    page.getByText(/lin@harbor.example · \+86 21 5555 0101/),
  ).toBeVisible();
  await page.getByRole("link", { name: "全部客商" }).click();
  await page.getByLabel("公司名称检索").fill("Harbor Unified");
  await page
    .getByRole("combobox", { name: "业务角色", exact: true })
    .selectOption("FORWARDER");
  await page.getByRole("button", { name: "检索档案" }).click();
  await page.getByRole("link", { name: /Harbor Unified Trading Ltd/ }).click();
  await expect(page.getByRole("heading", { name: "档案时间线" })).toBeVisible();
  await expect(page.getByText(/lin@harbor.example/)).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.operations_access_token);
  await expect(page.getByText("保密活动：待审核后开放").first()).toBeVisible();
  await expect(
    page.getByText("联系人确认电话号码", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText("审核文本开放范围", { exact: true })).toHaveCount(
    0,
  );
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  const entry = page
    .locator("li")
    .filter({ has: page.getByText("联系人确认电话号码", { exact: true }) });
  await entry
    .getByRole("button", { name: "审核文本开放范围", exact: true })
    .click();
  await entry.getByLabel("审核决定").selectOption("release");
  await entry
    .getByLabel("审核说明")
    .fill("已核对本条联系记录和全部补充信息，不含内部成本或利润");
  await entry.getByRole("checkbox").check();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await entry
      .locator(".document-review-form")
      .screenshot({ path: `test-results/company-text-review-${width}.png` });
  }
  await entry.getByRole("button", { name: "确认文本审核" }).click();
  await expect(
    page.getByText("本条文本已开放。", { exact: true }),
  ).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.operations_access_token);
  await expect(
    page.getByText("联系人确认电话号码", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("保密活动：待审核后开放").first()).toBeVisible();
  await expect(page.getByText("审核文本开放范围", { exact: true })).toHaveCount(
    0,
  );
});
