import { expect, test } from "@playwright/test";
import type { components } from "@trade-workbench/api-client";
import fs from "node:fs";
import path from "node:path";
type Fixture = {
  organization_id: string;
  access_token: string;
  manager_access_token: string;
  operations_access_token: string;
};
test("product directory reaches older matches and resets pages when searching", async ({
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
  ) as Fixture;
  const headers = {
    Authorization: `Bearer ${fixture.manager_access_token}`,
    "X-Organization-ID": fixture.organization_id,
  };
  for (let index = 0; index < 51; index += 1) {
    const suffix = String(index).padStart(3, "0");
    const response = await page.request.post(
      "http://127.0.0.1:8010/api/v1/products",
      {
        headers,
        data: {
          sku: `PAGING-${suffix}`,
          name: `Paging product ${suffix}`,
          unit: "set",
          standard_cost: "1.0000",
          cost_currency: "CNY",
        },
      },
    );
    expect(response.status()).toBe(201);
  }
  await page.addInitScript((session: Fixture) => {
    localStorage.setItem(
      "trade-workbench.organization-id",
      session.organization_id,
    );
    localStorage.setItem("trade-workbench.access-token", session.access_token);
  }, fixture);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/products");
  await page.getByLabel("产品名称或 SKU").fill("Paging product");
  await page.getByRole("button", { name: "检索产品" }).click();
  await expect(
    page.getByRole("link", { name: /Paging product 000/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "下一页产品" }).click();
  await expect(
    page.getByRole("link", { name: /Paging product 050/ }),
  ).toBeVisible();
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "下一页产品" })).toBeDisabled();
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
      path: `test-results/product-pagination-${width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "上一页产品" }).click();
  await expect(
    page.getByRole("link", { name: /Paging product 000/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "下一页产品" }).click();
  await expect(page.getByText("第 2 页", { exact: true })).toBeVisible();
  await page.getByLabel("产品名称或 SKU").fill("PAGING-000");
  await page.getByRole("button", { name: "检索产品" }).click();
  await expect(page.getByText("第 1 页", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Paging product 000/ }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "下一页产品" })).toBeDisabled();
});
test("links and revises supplier reference terms without repricing products", async ({
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
  ) as Fixture;
  const headers = {
    Authorization: `Bearer ${fixture.manager_access_token}`,
    "X-Organization-ID": fixture.organization_id,
    "Idempotency-Key": "supplier-browser-company",
  };
  const company = await page.request.post(
    "http://127.0.0.1:8010/api/v1/companies",
    { headers, data: { name: "Seaside Factory", roles: ["SUPPLIER"] } },
  );
  expect(company.status()).toBe(201);
  const product = await page.request.post(
    "http://127.0.0.1:8010/api/v1/products",
    {
      headers,
      data: {
        sku: "SUPPLIER-BROWSER",
        name: "316L Pump",
        unit: "set",
        standard_cost: "7.7777",
        cost_currency: "CNY",
      },
    },
  );
  expect(product.status()).toBe(201);
  const productData =
    (await product.json()) as components["schemas"]["ProductResponse"];
  await page.addInitScript((session: Fixture) => {
    localStorage.setItem(
      "trade-workbench.organization-id",
      session.organization_id,
    );
    localStorage.setItem(
      "trade-workbench.access-token",
      session.manager_access_token,
    );
  }, fixture);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/products");
  await page.getByLabel("产品名称或 SKU").fill("SUPPLIER-BROWSER");
  await page.getByRole("button", { name: "检索产品" }).click();
  await page.getByRole("link", { name: /316L Pump/ }).click();
  await page.getByRole("button", { name: "关联供应商", exact: true }).click();
  await page.getByRole("radio", { name: "Seaside Factory" }).check();
  await page.getByLabel("供应商货号", { exact: true }).fill("SS-PUMP-001");
  await page.getByLabel("参考单价", { exact: true }).fill("7.7777");
  await page.getByLabel("参考交期（天）").fill("21");
  await page.getByLabel("报价日期", { exact: true }).fill("2026-09-06");
  await page.getByLabel("有效截止日期（选填）").fill("2026-10-06");
  await page.getByLabel("报价来源或参考号（选填）").fill("Factory email 0609");
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
      path: `test-results/product-supplier-${width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "保存供应商参考" }).click();
  await expect(
    page.getByText("供应商参考已保存，历史业务快照保持不变。"),
  ).toBeVisible();
  await page.getByRole("button", { name: "更新参考 Seaside Factory" }).click();
  await page.getByLabel("参考单价", { exact: true }).fill("8.1250");
  await page.getByLabel("修改原因").fill("供应商确认新参考价格");
  await page.getByRole("button", { name: "保存供应商参考" }).click();
  await expect(
    page.getByText("供应商参考已保存，历史业务快照保持不变。"),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByText(/CNY 8.1250 \/ set/)).toBeVisible();
  await expect(
    page.getByText("供应商确认新参考价格", { exact: true }),
  ).toBeVisible();
  const unchanged = await page.request.get(
    `http://127.0.0.1:8010/api/v1/products/${productData.id}`,
    { headers },
  );
  expect((await unchanged.json()).standard_cost).toBe("7.7777");
  for (const [role, token] of [
    ["sales", fixture.access_token],
    ["operations", fixture.operations_access_token],
  ]) {
    const projected = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/v1/products/${productData.id}`) &&
        response.request().method() === "GET",
    );
    await page.evaluate((credential) => {
      localStorage.setItem("trade-workbench.access-token", credential);
      window.dispatchEvent(new Event("trade-workbench-session-change"));
    }, token);
    const body = await (await projected).json();
    expect(body.standard_cost).toBeNull();
    expect(body.cost_currency).toBeNull();
    await expect(
      page.getByRole("heading", { name: "316L Pump" }),
    ).toBeVisible();
    await expect(
      page.getByText(/当前成员无成本与供应商参考价格查看权限/),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "关联供应商", exact: true }),
    ).toHaveCount(0);
    await expect(page.getByText(/CNY 8.1250 \/ set/)).toHaveCount(0);
    const denied = await page.request.get(
      `http://127.0.0.1:8010/api/v1/products/${productData.id}/supplier-links`,
      {
        headers: { ...headers, Authorization: `Bearer ${token}` },
      },
    );
    expect(denied.status()).toBe(403);
    for (const width of [375, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: `test-results/catalog-${role}-${width}.png`,
        fullPage: true,
      });
    }
  }
});
