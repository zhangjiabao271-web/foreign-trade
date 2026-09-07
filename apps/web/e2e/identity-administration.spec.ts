import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("administrator manages organization and member access with explicit confirmation", async ({
  page,
}) => {
  test.setTimeout(90_000);
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
  await page.goto("/admin/organization");
  await page.getByRole("button", { name: "修改组织设置" }).click();
  await page
    .getByLabel("组织名称", { exact: true })
    .fill("Playwright Export Company Reviewed");
  await page.getByLabel("组织管理操作原因").fill("核实当前组织名称");
  await page.getByLabel("我已核对授权对象、操作原因和权限影响").check();
  await page.getByRole("button", { name: "保存组织设置", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Playwright Export Company Reviewed",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "添加已核实成员" }).click();
  await page
    .getByLabel("已核实的 Logto 用户标识")
    .fill("playwright-new-verified-member");
  await page.getByLabel("首次映射展示名").fill("验收成员");
  await page.getByLabel("组织管理操作原因").fill("仅用于隔离环境授权验收");
  await page.getByLabel("我已核对授权对象、操作原因和权限影响").check();
  await page.getByRole("button", { name: "确认添加成员", exact: true }).click();
  const member = page.locator("article").filter({
    has: page.getByRole("heading", { name: "验收成员", exact: true }),
  });
  await expect(member).toContainText("只读成员 · 已启用");
  await member.getByRole("button", { name: "调整角色" }).click();
  await page
    .getByRole("combobox", { name: "授权角色", exact: true })
    .selectOption("SALES");
  await page.getByLabel("组织管理操作原因").fill("核实销售工作职责");
  await page.getByLabel("我已核对授权对象、操作原因和权限影响").check();
  await page.getByRole("button", { name: "确认调整角色", exact: true }).click();
  await expect(member).toContainText("销售 · 已启用");
  await member.getByRole("button", { name: "停用成员", exact: true }).click();
  await page.getByLabel("组织管理操作原因").fill("验收停用访问权限");
  await page.getByLabel("我已核对授权对象、操作原因和权限影响").check();
  await page.getByRole("button", { name: "确认停用成员", exact: true }).click();
  await expect(member).toContainText("销售 · 已停用");
  await member.getByRole("button", { name: "重新启用成员" }).click();
  await page.getByLabel("组织管理操作原因").fill("验收恢复成员授权");
  await page.getByLabel("我已核对授权对象、操作原因和权限影响").check();
  await page.getByRole("button", { name: "确认重新启用", exact: true }).click();
  await expect(member).toContainText("销售 · 已启用");
  const administrator = page.locator("article").filter({
    has: page.getByRole("heading", { name: "Playwright Admin", exact: true }),
  });
  await administrator
    .getByRole("button", { name: "停用成员", exact: true })
    .click();
  await page.getByLabel("组织管理操作原因").fill("验证最后管理员保护");
  await page.getByLabel("我已核对授权对象、操作原因和权限影响").check();
  await page.getByRole("button", { name: "确认停用成员", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "不能移除最后一位有效管理员" }),
  ).toContainText("不能移除最后一位有效管理员");
  await page.getByRole("button", { name: "取消组织管理操作" }).click();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/identity-${width}.png`,
      fullPage: true,
    });
  }
});
