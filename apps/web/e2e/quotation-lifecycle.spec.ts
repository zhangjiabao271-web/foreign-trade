import { expect, test, type Page } from "@playwright/test";
import type { components } from "@trade-workbench/api-client";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { verifyUploadRecovery } from "./upload-recovery";

type Fixture = {
  organization_id: string;
  access_token: string;
  manager_access_token: string;
  operations_access_token: string;
};

const fixturePath = path.resolve(
  import.meta.dirname,
  "../../..",
  "test-results/e2e-fixture.json",
);

function loadFixture(): Fixture {
  return JSON.parse(fs.readFileSync(fixturePath, "utf-8")) as Fixture;
}

function processDocumentJobs(action = "process-documents") {
  const root = path.resolve(import.meta.dirname, "../../..");
  const python = path.join(
    root,
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  execFileSync(python, ["apps/api/scripts/e2e_fixture.py", action], {
    cwd: root,
    stdio: "inherit",
  });
}

async function reviewShipmentFile(
  page: Page,
  fixture: Fixture,
  fileName: string,
  versionNumber: number,
) {
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  const card = page
    .locator(".document-card")
    .filter({ hasText: fileName })
    .first();
  await expect(card).toBeVisible();
  await card.getByText("审核文件开放范围", { exact: true }).click();
  await card
    .getByRole("button", { name: `审核第 ${versionNumber} 版 · 保密` })
    .click();
  await card.getByLabel("审核决定").selectOption("release");
  await card
    .getByLabel("审核说明")
    .fill("已核对验收样例文件、标题和文件名，不含内部成本或利润");
  await card.getByRole("checkbox").check();
  if (fileName === "commercial-invoice.txt") {
    for (const width of [375, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width);
      await card
        .locator(".document-review-form")
        .screenshot({ path: `test-results/document-review-${width}.png` });
    }
  }
  await card.getByRole("button", { name: "确认审核决定" }).click();
  await expect(card.getByText("本版已开放。", { exact: true })).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.operations_access_token);
  await expect(card.getByText("审核文件开放范围", { exact: true })).toHaveCount(
    0,
  );
  await expect(card).toBeVisible();
}

async function verifyOrderCostRoles(page: Page) {
  const fixture = loadFixture();
  const headers = {
    Authorization: `Bearer ${fixture.manager_access_token}`,
    "X-Organization-ID": fixture.organization_id,
  };
  const response = await page.request.get(
    "http://127.0.0.1:8010/api/v1/sales-orders",
    { headers },
  );
  expect(response.ok()).toBeTruthy();
  const orders = (await response.json()).items;
  expect(orders.length).toBeGreaterThan(0);
  const original = orders[0];
  const purchaseResponse = await page.request.get(
    "http://127.0.0.1:8010/api/v1/purchase-orders?limit=100",
    { headers },
  );
  expect(purchaseResponse.ok()).toBeTruthy();
  const originalPurchases = (await purchaseResponse.json()).items;
  expect(originalPurchases.length).toBeGreaterThan(0);
  await page.goto(`/orders/${original.id}`);
  await expect(
    page.getByRole("table", { name: "接受版本冻结的销售订单行" }),
  ).toBeVisible();
  for (const [role, token, visible] of [
    ["manager", fixture.manager_access_token, true],
    ["sales", fixture.access_token, false],
    ["operations", fixture.operations_access_token, false],
  ] as const) {
    const read = page.waitForResponse(
      (result) =>
        result.request().method() === "GET" &&
        result.url().endsWith(`/sales-orders/${original.id}`) &&
        result.status() === 200,
    );
    await page.evaluate((accessToken) => {
      localStorage.setItem("trade-workbench.access-token", accessToken);
      window.dispatchEvent(new Event("trade-workbench-session-change"));
    }, token);
    const snapshot = await (await read).json();
    const roleHeaders = { ...headers, Authorization: `Bearer ${token}` };
    const purchases = await page.request.get(
      "http://127.0.0.1:8010/api/v1/purchase-orders?limit=100",
      { headers: roleHeaders },
    );
    expect(purchases.ok()).toBeTruthy();
    for (const purchase of (await purchases.json()).items) {
      const source = originalPurchases.find(
        (row: components["schemas"]["PurchaseOrderResponse"]) =>
          row.id === purchase.id,
      );
      expect(source).toBeTruthy();
      const detail = await page.request.get(
        `http://127.0.0.1:8010/api/v1/purchase-orders/${purchase.id}`,
        { headers: roleHeaders },
      );
      expect(detail.ok()).toBeTruthy();
      for (const projected of [purchase, await detail.json()]) {
        for (const field of [
          "currency_code",
          "exchange_rate",
          "total",
          "total_order_currency",
          "retained_total",
          "retained_total_order_currency",
        ]) {
          expect(projected[field]).toBe(visible ? source[field] : null);
        }
        for (let index = 0; index < projected.items.length; index += 1) {
          for (const field of ["unit_cost", "line_total"]) {
            expect(projected.items[index][field]).toBe(
              visible ? source.items[index][field] : null,
            );
          }
          expect(projected.items[index].received_quantity).toBe(
            source.items[index].received_quantity,
          );
        }
      }
    }
    for (const field of ["total_cost", "gross_profit", "gross_margin"]) {
      expect(snapshot[field]).toBe(visible ? original[field] : null);
    }
    for (let index = 0; index < snapshot.items.length; index += 1) {
      for (const field of [
        "unit_cost",
        "cost_currency",
        "cost_exchange_rate",
        "allocated_cost",
        "line_cost",
        "line_gross_profit",
      ]) {
        expect(snapshot.items[index][field]).toBe(
          visible ? original.items[index][field] : null,
        );
      }
      expect(snapshot.items[index].unit_price).toBe(
        original.items[index].unit_price,
      );
    }
    const table = page.getByRole("table", { name: "接受版本冻结的销售订单行" });
    await expect(table).toBeVisible();
    await expect(
      table.getByRole("columnheader", { name: "预计成本" }),
    ).toHaveCount(visible ? 1 : 0);
    await expect(
      table.getByRole("columnheader", { name: "毛利", exact: true }),
    ).toHaveCount(visible ? 1 : 0);
    await expect(
      table.getByRole("columnheader", { name: "售价" }),
    ).toBeVisible();
    for (const width of [375, 1440]) {
      await page.setViewportSize({ width, height: 950 });
      if (visible) {
        await expect(page.locator(".finance-timeline").first()).toContainText(
          "supplier_payment_allocation.reversed",
        );
      }
      const dimensions = await page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        scrollX,
      }));
      const overflow = await page.evaluate(() =>
        Array.from(document.querySelectorAll("body *"))
          .filter((element) => {
            const range = document.createRange();
            range.selectNodeContents(element);
            const rect = range.getBoundingClientRect();
            for (
              let ancestor = element.parentElement;
              ancestor;
              ancestor = ancestor.parentElement
            ) {
              if (getComputedStyle(ancestor).overflowX !== "visible")
                return false;
            }
            return (
              rect.right > innerWidth &&
              getComputedStyle(element).position !== "fixed"
            );
          })
          .map((element) => ({
            tag: element.tagName,
            className: element.className,
            text: element.textContent?.slice(0, 100),
            right: element.getBoundingClientRect().right,
            scrollWidth: element.scrollWidth,
            clientWidth: element.clientWidth,
          })),
      );
      expect(
        dimensions.scrollWidth,
        JSON.stringify(overflow),
      ).toBeLessThanOrEqual(dimensions.width);
      const tableRegion = page.locator(".quote-table-wrap");
      await tableRegion.screenshot({
        path: `test-results/order-snapshot-${role}-${width}.png`,
      });
      if (width === 375) {
        await tableRegion.evaluate((element) => {
          element.scrollLeft = element.scrollWidth;
        });
        await tableRegion.screenshot({
          path: `test-results/order-snapshot-${role}-${width}-amounts.png`,
        });
        await tableRegion.evaluate((element) => {
          element.scrollLeft = 0;
        });
      }
    }
  }
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

test("completes quotation, deposit, procurement, delivery, balance and order through the browser", async ({
  page,
}) => {
  const fixture = loadFixture();
  test.setTimeout(240_000);
  await page.goto("/leads");
  await page.getByRole("button", { name: "登记新线索" }).first().click();
  await page.getByLabel("公司名称 *").fill("North Sea Process BV");
  await page.getByLabel("联系人").fill("Eva de Vries");
  await page.getByRole("button", { name: "登记线索" }).click();
  await page.getByRole("button", { name: "确认有效" }).click();
  await page.getByRole("button", { name: "记录已联系" }).click();
  await page.getByRole("button", { name: "记录客户回复" }).click();
  await page.getByRole("button", { name: "转换为客户与商机" }).click();
  await expect(page.getByText("转换凭证已建立")).toBeVisible();
  const leadId = page.url().split("/").at(-1)!;
  const leadResponse = await page.request.get(
    `http://127.0.0.1:8010/api/v1/leads/${leadId}`,
    {
      headers: {
        Authorization: `Bearer ${fixture.access_token}`,
        "X-Organization-ID": fixture.organization_id,
      },
    },
  );
  expect(leadResponse.ok()).toBeTruthy();
  const lead =
    (await leadResponse.json()) as components["schemas"]["LeadDetailResponse"];

  await page.goto("/quotations");
  await expect(page.getByRole("heading", { name: "报价驾驶台" })).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  await page.getByRole("button", { name: "准备产品与询盘" }).click();
  await page.getByLabel("SKU *").fill("VALVE-E2E");
  await page.getByLabel("产品名称 *").fill("Sanitary control valve");
  await page
    .getByLabel("产品说明（默认保密）")
    .fill("Sanitary valve specification verified");
  await page.getByLabel("标准成本 *").fill("350.0000");
  await page.getByRole("button", { name: "保存产品" }).click();
  const productReceipt = await page.getByText(/^产品已建立：/).textContent();
  const productId = productReceipt!.split("：")[1]!;
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.access_token);
  await page.getByRole("button", { name: "准备产品与询盘" }).click();
  await page
    .getByLabel("商机 ID *")
    .fill(String(lead.converted_opportunity_id));
  await page
    .getByLabel("客户公司 ID *")
    .fill(String(lead.converted_company_id));
  await page.getByLabel("客户参考号").fill("E2E-RFQ-001");
  await page.getByLabel("询盘内容 *").fill("Two sanitary control valves");
  const inquiryKeys: string[] = [];
  const inquiryBodies: unknown[] = [];
  let committedInquiryId = "";
  await page.route("**/api/backend/api/v1/inquiries", async (route) => {
    const request = route.request();
    if (request.method() !== "POST") return route.continue();
    inquiryKeys.push(request.headers()["idempotency-key"] ?? "");
    inquiryBodies.push(request.postDataJSON());
    if (inquiryKeys.length === 1) {
      const response = await route.fetch();
      expect(response.status()).toBe(201);
      committedInquiryId = (await response.json()).id;
      return route.abort("failed");
    }
    return route.continue();
  });
  await page.getByRole("button", { name: "保存询盘" }).click();
  await expect(page.locator(".prep-panel").getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("询盘内容 *")).toHaveValue(
    "Two sanitary control valves",
  );
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/inquiry-create-retry-${width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "保存询盘" }).click();
  const inquiryReceipt = await page.getByText(/^询盘已建立：/).textContent();
  const inquiryId = inquiryReceipt!.split("：")[1]!;
  expect(inquiryId).toBe(committedInquiryId);
  expect(inquiryKeys).toHaveLength(2);
  expect(inquiryKeys[0]).toBeTruthy();
  expect(inquiryKeys[1]).toBe(inquiryKeys[0]);
  expect(inquiryBodies[1]).toEqual(inquiryBodies[0]);
  await page.unroute("**/api/backend/api/v1/inquiries");
  await page.getByRole("button", { name: "关闭" }).click();

  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  await page.getByRole("button", { name: "创建报价 V1" }).first().click();
  await page.getByLabel("询盘 ID *").fill(inquiryId);
  await page.getByLabel("报价币种 *").fill("EUR");
  await page.getByLabel("基准币种 *").fill("USD");
  await page.getByLabel("基准汇率 *").fill("1.08000000");
  await page
    .getByLabel("付款条件", { exact: true })
    .fill("30% deposit, balance before shipment");
  await page.getByLabel("有效期 *").fill("2000-01-01");
  await page.getByLabel("产品 ID *").fill(productId);
  await page.getByLabel("数量 *").fill("2.0000");
  await page.getByLabel("销售单价 *").fill("125.0000");
  await page.getByLabel("成本换算率 *").fill("0.12800000");
  await page.getByLabel("运费").fill("15.0000");
  await page.getByRole("button", { name: "添加一行" }).click();
  await page.getByLabel("产品 ID *").nth(1).fill(productId);
  await page.getByLabel("数量 *").nth(1).fill("3.0000");
  await page.getByLabel("销售单价 *").nth(1).fill("118.0000");
  await page.getByLabel("成本换算率 *").nth(1).fill("0.12800000");
  const creationKeys: string[] = [];
  let committedQuoteId = "";
  await page.route("**/api/backend/api/v1/quotations", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    creationKeys.push(route.request().headers()["idempotency-key"] ?? "");
    if (creationKeys.length === 1) {
      const response = await route.fetch();
      expect(response.status()).toBe(201);
      committedQuoteId = (await response.json()).id;
      return route.abort("failed");
    }
    return route.continue();
  });
  const createPanel = page.getByRole("region", { name: "创建报价 V1" });
  await createPanel.getByRole("button", { name: "创建报价 V1" }).click();
  await expect(createPanel.getByRole("alert")).toBeVisible();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect(createPanel).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/quotation-create-retry-${width}.png`,
      fullPage: true,
    });
  }
  await page
    .getByRole("region", { name: "创建报价 V1" })
    .getByRole("button", { name: "创建报价 V1" })
    .click();
  await expect(page).toHaveURL(/\/quotations\/[0-9a-f-]{36}$/);
  expect(page.url().split("/").at(-1)).toBe(committedQuoteId);
  expect(creationKeys).toHaveLength(2);
  expect(creationKeys[0]).toBeTruthy();
  expect(creationKeys[1]).toBe(creationKeys[0]);
  await page.unroute("**/api/backend/api/v1/quotations");
  const quoteDetail = page.locator(".quote-detail");
  await expect(
    quoteDetail.getByText("草稿", { exact: true }).first(),
  ).toBeVisible();

  const expiredQuoteId = page.url().split("/").at(-1)!;
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.access_token);
  for (const action of ["submit", "approve", "send"]) {
    const commandHeaders = {
      Authorization: `Bearer ${action === "approve" ? fixture.manager_access_token : fixture.access_token}`,
      "X-Organization-ID": fixture.organization_id,
    };
    const beforeCommand = await page.request.get(
      `http://127.0.0.1:8010/api/v1/quotations/${expiredQuoteId}`,
      { headers: commandHeaders },
    );
    const visibleVersion = (await beforeCommand.json()).current_version;
    const response = await page.request.post(
      `http://127.0.0.1:8010/api/v1/quotations/${expiredQuoteId}/${action}`,
      {
        headers: {
          ...commandHeaders,
          "Idempotency-Key": `prepare-${expiredQuoteId}-${action}`,
        },
        data: {
          expected_version_id: visibleVersion.id,
          expected_version: visibleVersion.version,
        },
      },
    );
    expect(response.status()).toBe(200);
  }
  await page.reload();
  await page.getByRole("button", { name: "记录客户接受", exact: true }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "QUOTATION_VALIDITY_ENDED" }),
  ).toBeVisible();
  await expect(
    quoteDetail.getByText("已发送", { exact: true }).first(),
  ).toBeVisible();
  const sourceResponse = await page.request.get(
    `http://127.0.0.1:8010/api/v1/quotations/${expiredQuoteId}`,
    {
      headers: {
        Authorization: `Bearer ${fixture.access_token}`,
        "X-Organization-ID": fixture.organization_id,
      },
    },
  );
  expect(sourceResponse.ok()).toBeTruthy();
  const sourceQuotation =
    (await sourceResponse.json()) as components["schemas"]["QuotationResponse"];
  const sourceItems = sourceQuotation.current_version.items;
  if (!sourceItems || sourceItems.length !== 2) {
    throw new Error("Revision fixture must expose both source quotation items");
  }
  await page.getByRole("button", { name: "生成修订版" }).click();
  await page.getByLabel("新有效期 *").fill("2026-12-31");
  await page.getByLabel("VALVE-E2E 新单价").nth(0).fill("132.5000");
  await page.getByLabel("VALVE-E2E 新单价").nth(1).fill("121.0000");
  const revisionKeys: string[] = [];
  let committedRevisionId = "";
  await page.route(
    "**/api/backend/api/v1/quotations/*/revisions",
    async (route) => {
      revisionKeys.push(route.request().headers()["idempotency-key"]);
      expect(route.request().postDataJSON().expected_version_id).toBeTruthy();
      for (const item of route.request().postDataJSON().items) {
        for (const field of [
          "unit_cost",
          "cost_currency",
          "cost_exchange_rate",
          "allocated_cost",
        ]) {
          expect(item).not.toHaveProperty(field);
        }
      }
      expect(
        route
          .request()
          .postDataJSON()
          .items.map(
            (item: components["schemas"]["QuotationRevisionItemInput"]) =>
              item.source_item_id,
          ),
      ).toEqual(sourceItems.map((item) => item.id));
      if (revisionKeys.length === 1) {
        const response = await route.fetch();
        expect(response.status()).toBe(201);
        committedRevisionId = (await response.json()).id;
        await route.abort("failed");
      } else {
        await route.continue();
      }
    },
  );
  await page.getByRole("button", { name: "生成 V2" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.getByRole("button", { name: "生成 V2" }).click();
  await expect(page.getByText("V2 商业快照")).toBeVisible();
  expect(revisionKeys).toHaveLength(2);
  expect(revisionKeys[0]).toBeTruthy();
  expect(revisionKeys[1]).toBe(revisionKeys[0]);
  const recoveredRevision = await page.request.get(
    `http://127.0.0.1:8010/api/v1/quotations/${page.url().split("/").at(-1)}`,
    {
      headers: {
        Authorization: `Bearer ${fixture.access_token}`,
        "X-Organization-ID": fixture.organization_id,
      },
    },
  );
  expect(recoveredRevision.ok()).toBeTruthy();
  const recoveredQuote = await recoveredRevision.json();
  expect(recoveredQuote.versions).toHaveLength(2);
  expect(recoveredQuote.current_version.id).toBe(committedRevisionId);
  await page.unroute("**/api/backend/api/v1/quotations/*/revisions");
  await expect(quoteDetail.getByText("已替代", { exact: true })).toBeVisible();
  // A separate authorized review changes the row counter without changing the commercial version.
  const reviewUrl = `http://127.0.0.1:8010/api/v1/commercial-text/quotation_version/${committedRevisionId}/review`;
  const reviewerHeaders = {
    Authorization: `Bearer ${fixture.manager_access_token}`,
    "X-Organization-ID": fixture.organization_id,
  };
  const beforeReview = await page.request.get(reviewUrl, {
    headers: reviewerHeaders,
  });
  expect(beforeReview.ok()).toBeTruthy();
  const reviewSnapshot = await beforeReview.json();
  const restricted = await page.request.post(reviewUrl, {
    headers: {
      ...reviewerHeaders,
      "Idempotency-Key": `stale-view-${committedRevisionId}`,
    },
    data: {
      expected_version: reviewSnapshot.version,
      content_digest: reviewSnapshot.content_digest,
      release: false,
      confirmed: true,
      reason: "Keep the current quotation text confidential during review",
    },
  });
  expect(restricted.ok()).toBeTruthy();
  const refreshedVersion = (await restricted.json()).version;
  await page.getByRole("button", { name: "提交审核" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "VERSION_CONFLICT" }),
  ).toBeVisible();
  await expect(
    quoteDetail.getByText("草稿", { exact: true }).first(),
  ).toBeVisible();
  await page.reload();
  const submitKeys: string[] = [];
  await page.route(
    "**/api/backend/api/v1/quotations/*/submit",
    async (route) => {
      const request = route.request();
      submitKeys.push(request.headers()["idempotency-key"] ?? "");
      expect(request.postDataJSON()).toEqual({
        expected_version_id: committedRevisionId,
        expected_version: refreshedVersion,
      });
      if (submitKeys.length === 1) {
        const response = await route.fetch();
        expect(response.status()).toBe(200);
        return route.abort("failed");
      }
      return route.continue();
    },
  );
  await page.getByRole("button", { name: "提交审核" }).click();
  await expect(
    page.getByRole("button", { name: "原样重试上次报价操作" }),
  ).toBeVisible();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/quotation-state-retry-${width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "原样重试上次报价操作" }).click();
  await expect(
    quoteDetail.getByText("内部审核", { exact: true }).first(),
  ).toBeVisible();
  expect(submitKeys).toHaveLength(2);
  expect(submitKeys[0]).toBeTruthy();
  expect(submitKeys[1]).toBe(submitKeys[0]);
  await page.unroute("**/api/backend/api/v1/quotations/*/submit");

  await page.evaluate((token) => {
    window.localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  await page.getByRole("button", { name: "经理批准" }).click();
  await expect(page.getByText(/已批准/)).toBeVisible();

  await page.evaluate((token) => {
    window.localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.access_token);
  await page.getByRole("button", { name: "发送给客户" }).click();
  await expect(
    quoteDetail.getByText("已发送", { exact: true }).first(),
  ).toBeVisible();
  const quoteUrl = page.url();
  await page.goto(`/opportunities/${lead.converted_opportunity_id}`);
  await page.getByRole("button", { name: "开始洽谈" }).click();
  await page.getByLabel("处理原因").fill("客户已核对 V2 价格，进入交期洽谈");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "开始洽谈", exact: true }).click();
  await expect(page.getByText("当前阶段 · 洽谈中")).toBeVisible();
  await page.goto(quoteUrl);
  await page
    .getByLabel("客户审阅依据")
    .fill("客户邮件确认正在审核 V2 的价格与交期");
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBeTruthy();
    await quoteDetail.screenshot({
      path: `test-results/customer-review-${width}.png`,
    });
  }
  await page.getByRole("button", { name: "记录客户审阅", exact: true }).click();
  await expect(
    quoteDetail.getByText("客户审核", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "记录客户审阅", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "记录客户接受" }).click();
  await expect(
    quoteDetail.getByText("已接受", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "生成修订版" })).toHaveCount(0);

  const quotationId = page.url().split("/").at(-1)!;
  const supplierRole = await page.request.post(
    `http://127.0.0.1:8010/api/v1/companies/${lead.converted_company_id}/roles`,
    {
      headers: {
        Authorization: `Bearer ${fixture.access_token}`,
        "X-Organization-ID": fixture.organization_id,
      },
      data: { role: "SUPPLIER" },
    },
  );
  expect(supplierRole.ok()).toBeTruthy();

  await page.goto("/orders");
  await expect(page.getByRole("heading", { name: "订单承诺舱" })).toBeVisible();
  await page.getByRole("button", { name: "从已接受报价建单" }).click();
  await page.getByLabel("已接受报价 ID *").fill(quotationId);
  await page.getByLabel("定金比例 *").fill("0.3000");
  await page.getByLabel("定金到期日").fill("2026-10-15");
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page
      .getByRole("region", { name: "冻结客户承诺" })
      .screenshot({ path: `test-results/order-create-form-${width}.png` });
  }
  let committedOrderId = "";
  let originalOrderBody = "";
  let originalOrderKey: string | undefined;
  let createOrderAttempts = 0;
  await page.route("**/api/backend/api/v1/sales-orders", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    createOrderAttempts += 1;
    const body = route.request().postData()!;
    const key = route.request().headers()["idempotency-key"];
    const response = await route.fetch();
    expect(response.status()).toBe(201);
    const result = await response.json();
    if (createOrderAttempts === 1) {
      originalOrderBody = body;
      originalOrderKey = key;
      committedOrderId = result.id;
      expect(key).toBeTruthy();
      return route.abort("failed");
    }
    expect(body).toBe(originalOrderBody);
    expect(key).toBe(originalOrderKey);
    expect(result.id).toBe(committedOrderId);
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "从报价生成订单" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "服务暂时不可用" }),
  ).toBeVisible();
  await expect(page.getByLabel("定金比例 *")).toHaveValue("0.3000");
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page
      .getByRole("region", { name: "冻结客户承诺" })
      .screenshot({ path: `test-results/order-create-retry-${width}.png` });
  }
  await page.getByRole("button", { name: "从报价生成订单" }).click();
  await expect(page).toHaveURL(/\/orders\/[0-9a-f-]{36}$/);
  const orderId = page.url().split("/").at(-1)!;
  expect(orderId).toBe(committedOrderId);
  expect(createOrderAttempts).toBe(2);
  await page.unroute("**/api/backend/api/v1/sales-orders");
  await expect(page.getByText("客户订单额")).toBeVisible();
  await expect(page.getByText("约定定金")).toBeVisible();

  await page.evaluate((token) => {
    window.localStorage.setItem("trade-workbench.access-token", token);
  }, fixture.manager_access_token);
  await page.evaluate(() =>
    window.dispatchEvent(new Event("trade-workbench-session-change")),
  );
  await expect(
    page.getByRole("button", { name: "经理确认订单" }),
  ).toBeVisible();
  const orderReviewUrl = `http://127.0.0.1:8010/api/v1/commercial-text/sales_order/${orderId}/review`;
  const orderReviewResponse = await page.request.get(orderReviewUrl, {
    headers: reviewerHeaders,
  });
  expect(orderReviewResponse.ok()).toBeTruthy();
  const orderReview = await orderReviewResponse.json();
  const orderRestriction = await page.request.post(orderReviewUrl, {
    headers: {
      ...reviewerHeaders,
      "Idempotency-Key": `stale-order-${orderId}`,
    },
    data: {
      expected_version: orderReview.version,
      content_digest: orderReview.content_digest,
      release: false,
      confirmed: true,
      reason: "Keep order text confidential during review",
    },
  });
  expect(orderRestriction.ok()).toBeTruthy();
  const currentOrderVersion = (await orderRestriction.json()).version;
  await page.getByRole("button", { name: "经理确认订单" }).click();
  await expect(
    page
      .locator(".order-detail")
      .getByRole("alert")
      .filter({ hasText: "VERSION_CONFLICT" }),
  ).toBeVisible();
  await page.reload();
  // The isolated fixture's init script resets each navigation to the sales actor.
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  const orderConfirmKeys: string[] = [];
  await page.route(
    "**/api/backend/api/v1/sales-orders/*/confirm",
    async (route) => {
      const request = route.request();
      orderConfirmKeys.push(request.headers()["idempotency-key"] ?? "");
      expect(request.postDataJSON()).toEqual({
        expected_version: currentOrderVersion,
      });
      if (orderConfirmKeys.length === 1) {
        const response = await route.fetch();
        expect(response.status()).toBe(200);
        expect((await response.json()).id).toBe(orderId);
        return route.abort("failed");
      }
      return route.continue();
    },
  );
  await page.getByRole("button", { name: "经理确认订单" }).click();
  await expect(
    page.getByRole("button", { name: "原样重试订单确认" }),
  ).toBeVisible();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/order-confirm-retry-${width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: "原样重试订单确认" }).click();
  const orderDetail = page.locator(".order-detail");
  await expect(
    orderDetail.getByText("待收定金", { exact: true }).first(),
  ).toBeVisible();
  expect(orderConfirmKeys).toHaveLength(2);
  expect(orderConfirmKeys[0]).toBeTruthy();
  expect(orderConfirmKeys[1]).toBe(orderConfirmKeys[0]);
  await page.unroute("**/api/backend/api/v1/sales-orders/*/confirm");

  const contracts = page.getByRole("region", { name: "销售合同", exact: true });
  await contracts
    .getByRole("button", { name: "建立合同草稿", exact: true })
    .click();
  await contracts.getByLabel("外部合同编号").fill("CUSTOMER-SC-E2E");
  await contracts
    .getByLabel("合同备注")
    .fill("Counterpart reviewed against accepted order");
  await contracts
    .getByRole("button", { name: "建立合同草稿", exact: true })
    .click();
  await expect(contracts.getByText(/合同操作已保存/)).toBeVisible();
  await contracts.getByRole("button", { name: "编辑合同备注" }).click();
  await contracts.getByLabel("合同操作原因").fill("核对客户合同编号");
  await contracts.getByLabel("外部合同编号").fill("CUSTOMER-SC-E2E-REVIEWED");
  await contracts.getByRole("button", { name: "保存合同备注" }).click();
  await expect(
    contracts.getByText("外部编号：CUSTOMER-SC-E2E-REVIEWED"),
  ).toBeVisible();
  const contractFile = {
    name: "e2e-signed-contract.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(
      "%PDF-1.4\nSynthetic signed contract acceptance fixture\n%%EOF",
    ),
  };
  await contracts.getByLabel("上传签署合同文件").setInputFiles(contractFile);
  await verifyUploadRecovery(
    page,
    contracts.getByRole("button", { name: "上传合同证据" }),
    contracts.getByRole("alert"),
    { resumeFile: contractFile },
  );
  processDocumentJobs();
  await contracts.getByRole("button", { name: "刷新合同证据" }).click();
  await expect(
    contracts.getByText(/e2e-signed-contract.pdf · 第 1 版：已验收/),
  ).toBeVisible();
  await contracts.getByRole("button", { name: "登记合同签署" }).click();
  await contracts.getByLabel("合同签署日期").fill("2026-09-01");
  await contracts.getByLabel("签署证据版本").selectOption({ index: 1 });
  await contracts.getByLabel("合同操作原因").fill("人工核验双方已签署合同");
  await contracts.getByLabel("我已核对签署文件与合同商业条款").check();
  await contracts.getByRole("button", { name: "确认登记已签署" }).click();
  await expect(
    contracts.getByRole("heading", { name: /已签署/ }),
  ).toBeVisible();
  await expect(
    contracts.getByRole("button", { name: "下载签署证据" }),
  ).toBeVisible();
  await expect(
    contracts.getByRole("button", { name: "编辑合同备注" }),
  ).toHaveCount(0);
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await contracts.screenshot({ path: `test-results/contracts-${width}.png` });
  }

  const expenses = page.getByRole("region", { name: "订单费用", exact: true });
  const funding = expenses.getByRole("region", {
    name: "垫资估算",
    exact: true,
  });
  await expect(funding.getByText("垫资估算 · 非实际现金缺口")).toBeVisible();
  await expect(funding.getByText(/额外费用净额：0.0000/)).toBeVisible();
  await expect(funding.getByText(/估算为零也不保证无需准备资金/)).toBeVisible();
  await expenses
    .getByRole("button", { name: "登记订单费用", exact: true })
    .click();
  await expenses.getByLabel("费用成本归类").selectOption("ADDITIONAL");
  await expenses.getByLabel("费用金额", { exact: true }).fill("12.3456");
  await expenses.getByLabel("费用发生日期").fill("2026-09-01");
  await expenses.getByLabel("费用说明").fill("已核对承运人附加运费");
  await expenses.getByLabel("凭证引用").fill("E2E-FREIGHT-001");
  await expenses.getByLabel("费用操作原因").fill("发票核对完成后登记");
  await expenses.getByLabel("我已核对凭证及归类，避免重复扣减报价成本").check();
  await expenses.getByRole("button", { name: "保存订单费用" }).click();
  await expect(expenses.getByText(/费用操作已保存/)).toBeVisible();
  await expect(expenses.getByText(/额外费用净额 12.3456/)).toBeVisible();
  await expect(funding.getByText(/额外费用净额：12.3456/)).toBeVisible();
  await expenses.getByRole("button", { name: /^冲销费用 EX/ }).click();
  await expenses.getByLabel("费用操作原因").fill("测试重复凭证全额冲销");
  await expenses.getByLabel("我确认全额冲销此费用").check();
  await expenses.getByRole("button", { name: "确认冲销费用" }).click();
  await expect(
    expenses.getByRole("heading", { name: /冲销记录/ }),
  ).toBeVisible();
  await expect(expenses.getByText(/额外费用净额 0.0000/)).toBeVisible();
  await expect(funding.getByText(/额外费用净额：0.0000/)).toBeVisible();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await expenses.screenshot({ path: `test-results/expenses-${width}.png` });
  }

  await page.getByLabel("定金到期日", { exact: true }).fill("2026-09-01");
  await page.getByLabel("尾款到期日").fill("2026-12-31");
  await page.getByRole("button", { name: "生成定金和尾款应收" }).click();
  await expect(page.getByText("定金 · 逾期", { exact: true })).toBeVisible();
  const receivableResponse = await page.request.get(
    `http://127.0.0.1:8010/api/v1/receivables?sales_order_id=${orderId}`,
    {
      headers: {
        Authorization: `Bearer ${fixture.manager_access_token}`,
        "X-Organization-ID": fixture.organization_id,
      },
    },
  );
  expect(receivableResponse.ok()).toBeTruthy();
  const receivablePage =
    (await receivableResponse.json()) as components["schemas"]["ReceivableListResponse"];
  const installments = receivablePage.items;
  const deposit = installments.find(
    (row) => row.installment_type === "DEPOSIT",
  )!;
  const balance = installments.find(
    (row) => row.installment_type === "BALANCE",
  )!;
  // Newer, unallocated customer receipts must not hide an older settlement receipt.
  for (let index = 0; index < 21; index += 1) {
    const seeded = await page.request.post(
      "http://127.0.0.1:8010/api/v1/payments",
      {
        headers: {
          Authorization: `Bearer ${fixture.manager_access_token}`,
          "X-Organization-ID": fixture.organization_id,
          "Idempotency-Key": crypto.randomUUID(),
        },
        data: {
          company_id: lead.converted_company_id,
          amount: "1.0000",
          currency_code: "EUR",
          method: "BANK_TRANSFER",
          received_at: "2026-10-01T00:00:00Z",
          reference: `PAGE-FILLER-${index}`,
        },
      },
    );
    expect(seeded.ok()).toBeTruthy();
  }
  async function settle(installment: typeof deposit, reference: string) {
    await page.getByLabel("实收金额").fill(installment.amount);
    await page.getByLabel("收款日期").fill("2026-09-05");
    await page.getByLabel("银行流水号").fill(reference);
    await page
      .getByLabel("收款备注（默认保密）")
      .fill("已核对客户本次汇款用途");
    await page.getByRole("button", { name: "记录收款", exact: true }).click();
    await expect(
      page.getByText("收款已记录，请在右侧核销到对应应收。"),
    ).toBeVisible();
    const response = await page.request.get(
      "http://127.0.0.1:8010/api/v1/payments",
      {
        headers: {
          Authorization: `Bearer ${fixture.manager_access_token}`,
          "X-Organization-ID": fixture.organization_id,
        },
      },
    );
    const receiptPage =
      (await response.json()) as components["schemas"]["PaymentListResponse"];
    const receipts = receiptPage.items;
    const receipt = receipts.find((row) => row.reference === reference)!;
    await page.getByRole("button", { name: "下一页收款" }).click();
    await expect(
      page
        .getByRole("navigation", { name: "收款分页", exact: true })
        .getByText("第 2 页", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByLabel("选择收款").locator(`option[value="${receipt.id}"]`),
    ).toHaveCount(1);
    await page.getByLabel("查找当前客户收款").fill(reference);
    await page.getByRole("button", { name: "查找收款", exact: true }).click();
    await expect(
      page
        .getByRole("navigation", { name: "收款分页", exact: true })
        .getByText("第 1 页", { exact: true }),
    ).toBeVisible();
    await page.getByLabel("选择收款").selectOption(receipt.id);
    await page.getByLabel("选择应收").selectOption(installment.id);
    await page.getByLabel("核销金额").fill(installment.amount);
    await page.getByRole("button", { name: "确认核销" }).click();
    await expect(page.getByLabel("核销金额")).toHaveValue("");
    if (reference === "E2E-DEPOSIT") {
      const card = page.locator(`[data-payment-id="${receipt.id}"]`);
      const notes = card.getByRole("region", { name: "收款备注审核" });
      async function selectRole(token: string) {
        await page.evaluate((value) => {
          localStorage.setItem("trade-workbench.access-token", value);
          window.dispatchEvent(new Event("trade-workbench-session-change"));
        }, token);
        await page.getByLabel("查找当前客户收款").fill(reference);
        await page
          .getByRole("button", { name: "查找收款", exact: true })
          .click();
        await expect(card).toBeVisible();
      }
      await selectRole(fixture.operations_access_token);
      await expect(
        page.getByRole("region", { name: "垫资估算", exact: true }),
      ).toHaveCount(0);
      await expect(notes.getByText("收款备注待审核，当前不可见")).toBeVisible();
      await expect(
        card.getByText(`银行流水号：${reference}`, { exact: false }),
      ).toBeVisible();
      await selectRole(fixture.manager_access_token);
      await notes.getByRole("button", { name: "审核文本开放范围" }).click();
      await notes.getByLabel("审核决定").selectOption("release");
      await notes
        .getByLabel("审核说明")
        .fill("已核对本次收款备注，不含成本利润");
      await notes.getByRole("checkbox").check();
      for (const width of [375, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth),
        ).toBeLessThanOrEqual(width);
        await notes.screenshot({
          path: `test-results/payment-source-review-${width}.png`,
        });
      }
      await notes.getByRole("button", { name: "确认文本审核" }).click();
      await expect(
        notes.getByText("本条文本已开放。", { exact: true }),
      ).toBeVisible();
      await selectRole(fixture.operations_access_token);
      await expect(
        notes.getByText("已核对客户本次汇款用途", { exact: true }),
      ).toBeVisible();
      await expect(notes.getByText("审核文本开放范围")).toHaveCount(0);
      await selectRole(fixture.manager_access_token);
    }
    await page.getByLabel("查找当前客户收款").fill("");
    await page.getByRole("button", { name: "查找收款", exact: true }).click();
  }
  await settle(deposit, "E2E-DEPOSIT");
  await expect(
    funding.getByText(`本订单净核销收款：${deposit.amount} EUR`),
  ).toBeVisible();
  await expect(
    orderDetail.getByText("执行中", { exact: true }).first(),
  ).toBeVisible();

  const orderUrl = page.url();
  const aiOrderId = orderUrl.split("/").at(-1)!;
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.access_token);
  await page.goto("/copilot");
  await page.getByLabel("辅助类型").selectOption("TASK_DRAFT");
  await page.getByLabel("订单 ID", { exact: true }).fill(aiOrderId);
  await page.getByRole("button", { name: "开始辅助工作", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "建议内部跟进任务", exact: true }),
  ).toBeVisible();
  processDocumentJobs("process-ai");
  await expect(
    page.getByRole("button", { name: "提交内容审核", exact: true }),
  ).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("建议任务：复核订单文件准备进度")).toHaveCount(0);
  await page.getByLabel("我同意将这一条草稿提交内容审核").check();
  await page.getByRole("button", { name: "提交内容审核", exact: true }).click();
  await expect(
    page.getByText("候选正文受保护。", { exact: true }),
  ).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  await expect(
    page.getByRole("heading", { name: "本次完整候选内容" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "建议内部跟进任务 · 已生成",
      exact: true,
    }),
  ).toHaveCount(0);
  await page
    .getByLabel("脱敏草稿", { exact: true })
    .fill("请核对本订单文件准备进度，勿对外承诺新交期。已核验公开版本。");
  await page.getByRole("button", { name: "保存新候选，重新审核" }).click();
  const candidate = page.getByRole("article").filter({
    has: page.getByRole("heading", { name: "候选版本 2", exact: true }),
  });
  await candidate
    .getByRole("combobox", { name: "内容决定", exact: true })
    .selectOption("release");
  await candidate
    .getByLabel("内容审核理由", { exact: true })
    .fill("已核对全部候选正文，不含成本利润");
  await candidate.getByRole("checkbox").check();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await page.screenshot({
      path: `test-results/ai-disclosure-${width}.png`,
      fullPage: true,
    });
  }
  await candidate.getByRole("button", { name: "记录内容决定" }).click();
  await expect(
    candidate.getByText("状态：已审核开放", { exact: true }),
  ).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.access_token);
  await page
    .getByRole("button", { name: "建议内部跟进任务 · 已生成", exact: true })
    .click();
  await expect(page.getByText("建议任务：复核订单文件准备进度")).toBeVisible({
    timeout: 15000,
  });
  await page
    .getByLabel("提交任务建议供人工审核的理由")
    .fill("请经理确认这项内部跟进任务");
  await page
    .getByRole("button", { name: "提交任务建议供人工审核", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "任务审批正文受保护", exact: true }),
  ).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  await page
    .getByLabel("批准并创建内部任务的理由")
    .fill("已核实，仅创建内部任务");
  await page
    .getByRole("button", { name: "批准并创建内部任务", exact: true })
    .click();
  await expect(
    page.getByText("已批准并创建任务", { exact: true }),
  ).toBeVisible();
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: `test-results/copilot-approval-${width}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(orderUrl);

  await page.evaluate((token) => {
    window.localStorage.setItem("trade-workbench.access-token", token);
  }, fixture.manager_access_token);
  await page.evaluate(() =>
    window.dispatchEvent(new Event("trade-workbench-session-change")),
  );
  await page.getByRole("button", { name: "创建采购单" }).click();
  await page
    .getByLabel("供应商公司 ID *")
    .fill(String(lead.converted_company_id));
  await page.getByLabel("采购币种 *").fill("CNY");
  await page.getByLabel("换算到订单币种汇率 *").fill("0.12800000");
  await page.getByLabel("VALVE-E2E 采购数量").nth(0).fill("2.0000");
  await page.getByLabel("VALVE-E2E 采购数量").nth(1).fill("3.0000");
  await page.getByLabel("VALVE-E2E 采购单价").nth(0).fill("350.0000");
  await page.getByLabel("VALVE-E2E 采购单价").nth(1).fill("350.0000");
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page
      .getByRole("region", { name: /建采购单/ })
      .screenshot({ path: `test-results/purchase-create-form-${width}.png` });
  }
  const purchaseCreateRoute = "**/api/backend/api/v1/purchase-orders";
  let purchaseCreateAttempts = 0;
  let originalPurchaseKey: string | undefined;
  await page.route(purchaseCreateRoute, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    purchaseCreateAttempts += 1;
    const key = route.request().headers()["idempotency-key"];
    expect(key).toBeTruthy();
    if (purchaseCreateAttempts === 1) {
      originalPurchaseKey = key;
      const committed = await route.fetch();
      expect(committed.status()).toBe(201);
      return route.abort("failed");
    }
    expect(key).toBe(originalPurchaseKey);
    return route.continue();
  });
  await page.getByRole("button", { name: "创建采购草稿" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "服务暂时不可用" }),
  ).toBeVisible();
  await expect(page.getByLabel("VALVE-E2E 采购单价").nth(0)).toHaveValue(
    "350.0000",
  );
  await page.getByRole("button", { name: "创建采购草稿" }).click();
  await expect(page.getByText(/PO-2026-/)).toBeVisible();
  await expect(page.locator(".purchase-card")).toHaveCount(1);
  expect(purchaseCreateAttempts).toBe(2);
  await page.unroute(purchaseCreateRoute);

  await page.evaluate((token) => {
    window.localStorage.setItem("trade-workbench.access-token", token);
  }, fixture.manager_access_token);
  await page.evaluate(() =>
    window.dispatchEvent(new Event("trade-workbench-session-change")),
  );
  await page.getByRole("button", { name: "批准采购单" }).click();
  await expect(page.getByText("已批准", { exact: true })).toBeVisible();

  await page.evaluate((token) => {
    window.localStorage.setItem("trade-workbench.access-token", token);
  }, fixture.operations_access_token);
  await page.evaluate(() =>
    window.dispatchEvent(new Event("trade-workbench-session-change")),
  );
  await page.getByRole("button", { name: "记录已发送" }).click();
  await page.getByRole("button", { name: "记录供应商确认" }).click();
  await page.getByLabel("供应商确认号").fill("E2E-SUP-ACK-1");
  await page.getByLabel("预计交付日 *").fill("2026-11-05");
  await page.getByRole("button", { name: "保存确认" }).click();
  await expect(page.getByText("供应商已确认", { exact: true })).toBeVisible();
  await expect(page.getByText("原采购额", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "变更采购", exact: true }),
  ).toHaveCount(0);
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  await page.getByRole("button", { name: "变更采购", exact: true }).click();
  await page
    .getByLabel("取消或变更原因")
    .fill("未收货部分调整价格，保留原单凭证");
  await page.getByLabel("供应商取消依据").fill("E2E-AMEND-SUPPLIER-ACK");
  await page.getByLabel("VALVE-E2E 替代数量").nth(0).fill("2.0000");
  await page.getByLabel("VALVE-E2E 替代数量").nth(1).fill("3.0000");
  await page.getByLabel("VALVE-E2E 新采购单价").nth(0).fill("349.0000");
  await page.getByLabel("VALVE-E2E 新采购单价").nth(1).fill("351.0000");
  await page.getByLabel("已核对供应商依据，确认保留已收货事实").check();
  await page.getByRole("button", { name: "确认变更并生成新草稿" }).click();
  await expect(page.locator(".purchase-card")).toHaveCount(2);
  const activePurchase = page
    .locator(".purchase-card")
    .filter({ has: page.getByText(/替代原采购单：/) });
  await expect(activePurchase.getByText("草稿", { exact: true })).toBeVisible();
  await expect(
    page.locator(".purchase-card").getByText("已取消", { exact: true }),
  ).toBeVisible();
  const purchaseListResponse = await page.request.get(
    "http://127.0.0.1:8010/api/v1/purchase-orders?limit=100",
    { headers: reviewerHeaders },
  );
  expect(purchaseListResponse.ok()).toBeTruthy();
  const replacementPurchase = (await purchaseListResponse.json()).items.find(
    (candidate: components["schemas"]["PurchaseOrderResponse"]) =>
      candidate.sales_order_id === orderId &&
      candidate.replaces_purchase_order_id !== null,
  );
  expect(replacementPurchase).toBeTruthy();
  const purchaseReviewUrl = `http://127.0.0.1:8010/api/v1/purchase-orders/${replacementPurchase.id}/text-review`;
  const purchaseReviewResponse = await page.request.get(purchaseReviewUrl, {
    headers: reviewerHeaders,
  });
  expect(purchaseReviewResponse.ok()).toBeTruthy();
  const purchaseReview = await purchaseReviewResponse.json();
  const restrictPurchase = await page.request.post(purchaseReviewUrl, {
    headers: { ...reviewerHeaders, "Idempotency-Key": crypto.randomUUID() },
    data: {
      expected_version: purchaseReview.version,
      content_digest: purchaseReview.content_digest,
      release: false,
      confirmed: true,
      reason: "独立审核保持保密，用于验证旧审批页面不得覆盖新版本",
    },
  });
  expect(restrictPurchase.ok()).toBeTruthy();
  await activePurchase.getByRole("button", { name: "批准采购单" }).click();
  await expect(
    activePurchase.getByRole("alert").filter({ hasText: "VERSION_CONFLICT" }),
  ).toBeVisible();
  await page.reload();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);

  async function recoverPurchaseDecision(
    action: "approve" | "send" | "confirm",
    label: string,
  ) {
    const routePattern = `**/api/backend/api/v1/purchase-orders/*/${action}`;
    let originalBody: string | null = null;
    let originalKey: string | undefined;
    let attempts = 0;
    await page.route(routePattern, async (route) => {
      attempts += 1;
      const body = route.request().postData();
      const key = route.request().headers()["idempotency-key"];
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      expect((await response.json()).id).toBe(replacementPurchase.id);
      if (attempts === 1) {
        originalBody = body;
        originalKey = key;
        expect(key).toBeTruthy();
        return route.abort("failed");
      }
      expect(body).toBe(originalBody);
      expect(key).toBe(originalKey);
      await route.fulfill({ response });
    });
    await activePurchase
      .getByRole("button", { name: label, exact: true })
      .click();
    await expect(
      activePurchase.getByRole("button", { name: "原样重试采购操作" }),
    ).toBeVisible();
    if (action === "confirm") {
      await expect(activePurchase.getByLabel("供应商确认号")).toHaveValue(
        "E2E-REPLACEMENT-ACK",
      );
      for (const width of [375, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        await expect
          .poll(() =>
            page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
          )
          .toBe(true);
        await activePurchase.screenshot({
          path: `test-results/purchase-decision-retry-${width}.png`,
        });
      }
    }
    await activePurchase
      .getByRole("button", { name: "原样重试采购操作" })
      .click();
    await expect(
      activePurchase.getByRole("button", { name: "原样重试采购操作" }),
    ).toHaveCount(0);
    await expect(
      activePurchase.getByText(
        { approve: "已批准", send: "已发送", confirm: "供应商已确认" }[action],
        { exact: true },
      ),
    ).toBeVisible();
    expect(attempts).toBe(2);
    await page.unroute(routePattern);
  }
  await recoverPurchaseDecision("approve", "批准采购单");
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.operations_access_token);
  await recoverPurchaseDecision("send", "记录已发送");
  await activePurchase.getByRole("button", { name: "记录供应商确认" }).click();
  await activePurchase.getByLabel("供应商确认号").fill("E2E-REPLACEMENT-ACK");
  await activePurchase.getByLabel("预计交付日 *").fill("2026-11-05");
  await recoverPurchaseDecision("confirm", "保存确认");
  await expect(
    activePurchase.getByText("供应商已确认", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "记录收货", exact: true }).click();
  await page.getByLabel("收货凭证号或说明").fill("E2E-RECEIPT-PARTIAL");
  await page.getByLabel("收货日期", { exact: true }).fill("2026-09-05");
  await page.getByLabel("VALVE-E2E 本次收货量").nth(0).fill("1.0000");
  await page.getByRole("button", { name: "确认本次收货" }).click();
  await expect(page.getByText("部分收货", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "记录收货", exact: true }).click();
  await page.getByLabel("收货凭证号或说明").fill("E2E-RECEIPT-REMAINING");
  await page.getByLabel("收货日期", { exact: true }).fill("2026-09-05");
  await page.getByLabel("VALVE-E2E 本次收货量").nth(0).fill("1.0000");
  await page.getByLabel("VALVE-E2E 本次收货量").nth(1).fill("3.0000");
  await page.getByRole("button", { name: "确认本次收货" }).click();
  await expect(page.getByText("已收货", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "关闭采购单", exact: true }).click();
  await page.getByLabel("关闭原因").fill("全部数量已核对，采购履约结束");
  await page.getByRole("button", { name: "确认关闭采购单" }).click();
  await expect(page.getByText("已关闭", { exact: true })).toBeVisible();
  await activePurchase.getByRole("button", { name: "查看采购记录" }).click();
  await expect(
    page
      .getByRole("region", { name: "采购操作记录" })
      .getByText("已登记采购收货", { exact: true })
      .first(),
  ).toBeVisible();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await activePurchase.screenshot({
      path: `test-results/purchase-receiving-${width}.png`,
    });
  }
  await activePurchase.getByRole("button", { name: "收起采购记录" }).click();

  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  await activePurchase.getByRole("button", { name: "查看采购记录" }).click();
  const receiptHistory = activePurchase
    .getByRole("region", { name: "采购操作记录" })
    .getByRole("listitem")
    .filter({ hasText: "E2E-RECEIPT-REMAINING" });
  await receiptHistory
    .getByRole("button", { name: "审核文本开放范围", exact: true })
    .click();
  await receiptHistory.getByLabel("审核决定").selectOption("release");
  await receiptHistory
    .getByLabel("审核说明")
    .fill("已核对收货凭证和全部补充内容，不含成本利润");
  await receiptHistory.getByRole("checkbox").check();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await receiptHistory.screenshot({
      path: `test-results/purchase-history-review-${width}.png`,
    });
  }
  await receiptHistory.getByRole("button", { name: "确认文本审核" }).click();
  await expect(
    receiptHistory.getByText("本条文本已开放。", { exact: true }),
  ).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.operations_access_token);
  await activePurchase.getByRole("button", { name: "查看采购记录" }).click();
  await expect(receiptHistory.getByText(/E2E-RECEIPT-REMAINING/)).toBeVisible();
  await expect(
    activePurchase.getByText("采购说明和取消正文待审核，当前不可见", {
      exact: true,
    }),
  ).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  await activePurchase.getByRole("button", { name: "查看供应商结算" }).click();
  const supplierFinance = activePurchase.getByRole("region", {
    name: /^供应商结算 PO/,
  });
  await supplierFinance.getByRole("button", { name: "登记供应商应付" }).click();
  await supplierFinance.getByLabel("供应商结算金额").fill("100.0000");
  await supplierFinance.getByLabel("供应商业务日期").fill("2026-09-01");
  await supplierFinance
    .getByLabel("供应商凭证引用")
    .fill("E2E-SUPPLIER-INVOICE");
  await supplierFinance.getByLabel("应付到期日").fill("2026-09-02");
  await supplierFinance.getByLabel("应付说明").fill("人工核对采购本金分期应付");
  await supplierFinance.getByLabel("供应商结算操作原因").fill("核验供应商发票");
  await supplierFinance.getByLabel("我已核对供应商凭证并确认本次操作").check();
  await supplierFinance.getByRole("button", { name: "保存供应商应付" }).click();
  await expect(
    supplierFinance.getByText("待付 100.0000 CNY", { exact: true }),
  ).toBeVisible();
  for (const round of [1, 2]) {
    await supplierFinance
      .getByRole("button", { name: "登记供应商付款" })
      .click();
    await supplierFinance.getByLabel("供应商结算金额").fill("100.0000");
    await supplierFinance.getByLabel("供应商业务日期").fill("2026-09-01");
    await supplierFinance
      .getByLabel("供应商凭证引用")
      .fill(`E2E-SUPPLIER-BANK-${round}`);
    await supplierFinance
      .getByLabel("供应商结算操作原因")
      .fill("核验已发生的银行付款");
    await supplierFinance
      .getByLabel("我已核对供应商凭证并确认本次操作")
      .check();
    await supplierFinance
      .getByRole("button", { name: "保存供应商付款" })
      .click();
    await supplierFinance.getByRole("button", { name: /^核销付款 SP/ }).click();
    await supplierFinance
      .getByLabel("待核销供应商应付")
      .selectOption({ index: 1 });
    await supplierFinance.getByLabel("供应商结算金额").fill("100.0000");
    await supplierFinance
      .getByLabel("供应商结算操作原因")
      .fill("核对采购发票与付款");
    await supplierFinance
      .getByLabel("我已核对供应商凭证并确认本次操作")
      .check();
    await supplierFinance
      .getByRole("button", { name: "确认供应商核销" })
      .click();
    await expect(
      supplierFinance.getByRole("heading", { name: /AP-.*已结清/ }),
    ).toBeVisible();
    if (round === 1) {
      await supplierFinance
        .getByRole("button", { name: /^冲销付款 SP/ })
        .click();
      await supplierFinance
        .getByLabel("供应商结算操作原因")
        .fill("纠正重复付款凭证，不代表银行退款");
      await supplierFinance
        .getByLabel("我已核对供应商凭证并确认本次操作")
        .check();
      await supplierFinance
        .getByRole("button", { name: "确认冲销供应商付款" })
        .click();
      await expect(
        supplierFinance.getByText("待付 100.0000 CNY", { exact: true }),
      ).toBeVisible();
    }
  }
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await supplierFinance.screenshot({
      path: `test-results/supplier-finance-${width}.png`,
    });
  }

  await page.goto("/shipments");
  await page.evaluate((token) => {
    window.localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.operations_access_token);
  await expect(page.getByRole("heading", { name: "出运航控台" })).toBeVisible();
  await page.getByRole("button", { name: "创建出运计划" }).click();
  await page.getByLabel("计划离港日").fill("2026-11-10");
  await page.getByLabel("计划到港日").fill("2026-12-02");
  const cargoLines = page.getByRole("checkbox");
  await expect(cargoLines).toHaveCount(2);
  await cargoLines.nth(0).check();
  await cargoLines.nth(1).check();
  await page.getByLabel("VALVE-E2E 本次出运数量").nth(0).fill("2.0000");
  await page.getByLabel("VALVE-E2E 本次出运数量").nth(1).fill("3.0000");
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page
      .getByRole("region", { name: "编排本次装运" })
      .screenshot({ path: `test-results/shipment-create-${width}.png` });
  }
  const shipmentCreateRoute = "**/api/backend/api/v1/shipments";
  let shipmentAttempts = 0;
  let shipmentKey: string | undefined;
  await page.route(shipmentCreateRoute, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    shipmentAttempts += 1;
    const key = route.request().headers()["idempotency-key"];
    expect(key).toBeTruthy();
    if (shipmentAttempts === 1) {
      shipmentKey = key;
      const committed = await route.fetch();
      expect(committed.status()).toBe(201);
      return route.abort("failed");
    }
    expect(key).toBe(shipmentKey);
    return route.continue();
  });
  const createShipmentButton = page
    .getByRole("region", { name: "编排本次装运" })
    .getByRole("button", { name: "创建出运计划" });
  await createShipmentButton.click();
  await expect(
    page.getByRole("alert").filter({ hasText: "服务暂时不可用" }),
  ).toBeVisible();
  await expect(page.getByLabel("VALVE-E2E 本次出运数量").nth(0)).toHaveValue(
    "2.0000",
  );
  await page
    .getByRole("region", { name: "编排本次装运" })
    .getByRole("button", { name: "创建出运计划" })
    .click();
  await expect(page).toHaveURL(/\/shipments\/[0-9a-f-]{36}$/);
  expect(shipmentAttempts).toBe(2);
  await expect(page.locator(".shipment-row")).toHaveCount(1);
  await page.unroute(shipmentCreateRoute);
  const shipmentId = page.url().split("/").at(-1)!;
  async function recoverShipmentDecision(
    action: string,
    label: string,
    targetLabel: string,
  ) {
    const routePattern = `**/api/backend/api/v1/shipments/${shipmentId}/${action}`;
    let originalBody: string | null = null;
    let originalKey: string | undefined;
    let attempts = 0;
    await page.route(routePattern, async (route) => {
      attempts += 1;
      const body = route.request().postData();
      const key = route.request().headers()["idempotency-key"];
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      expect((await response.json()).id).toBe(shipmentId);
      if (attempts === 1) {
        originalBody = body;
        originalKey = key;
        expect(key).toBeTruthy();
        expect(JSON.parse(body!).expected_version).toBeGreaterThan(0);
        return route.abort("failed");
      }
      expect(body).toBe(originalBody);
      expect(key).toBe(originalKey);
      await route.fulfill({ response });
    });
    await page.getByRole("button", { name: label, exact: true }).click();
    await expect(
      page.getByRole("button", { name: "原样重试出运操作" }),
    ).toBeVisible();
    if (action === "book") {
      await expect(page.getByLabel("订舱参考号 *")).toHaveValue(
        "E2E-BOOKING-001",
      );
      for (const width of [375, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        await expect
          .poll(() =>
            page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
          )
          .toBe(true);
        await page.locator(".booking-form").screenshot({
          path: `test-results/shipment-decision-retry-${width}.png`,
        });
      }
    }
    await page.getByRole("button", { name: "原样重试出运操作" }).click();
    await expect(
      page.getByRole("button", { name: "原样重试出运操作" }),
    ).toHaveCount(0);
    await expect(
      page.locator(".shipment-detail .status-chip.large"),
    ).toHaveText(targetLabel);
    expect(attempts).toBe(2);
    await page.unroute(routePattern);
  }
  await expect(page.getByRole("list", { name: "出运进度" })).toBeVisible();
  await expect(page.getByText("2 行", { exact: true })).toBeVisible();

  await page.getByLabel("订舱参考号 *").fill("E2E-BOOKING-001");
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page
      .locator(".booking-form")
      .screenshot({ path: `test-results/shipment-booking-${width}.png` });
  }
  await recoverShipmentDecision("book", "记录已订舱", "已订舱");
  await expect(page.getByText("已订舱", { exact: true }).first()).toBeVisible();

  await page.getByRole("button", { name: "确认文件齐备" }).click();
  await expect(
    page.getByText("商业发票与装箱单必须完成上传和扫描后，才能推进出运。"),
  ).toBeVisible();

  const fileInput = page.getByLabel("选择文件（最大 25 MB）");
  const uploadRoute = "**/api/backend/api/v1/documents/upload-sessions";
  const completeRoute = "**/api/backend/api/v1/documents/*/versions/*/complete";
  let uploadAttempts = 0;
  let uploadKey: string | undefined;
  let recoveredDocumentId: string | undefined;
  await page.route(uploadRoute, async (route) => {
    uploadAttempts += 1;
    const key = route.request().headers()["idempotency-key"];
    expect(key).toBeTruthy();
    const response = await route.fetch();
    expect(response.status()).toBe(201);
    const body = await response.json();
    if (uploadAttempts === 1) {
      uploadKey = key;
      recoveredDocumentId = body.document.id;
      return route.abort("failed");
    }
    expect(key).toBe(uploadKey);
    expect(body.document.id).toBe(recoveredDocumentId);
    if (uploadAttempts === 3) expect(body.upload_url).toBeNull();
    return route.fulfill({ response });
  });
  let completeAttempts = 0;
  await page.route(completeRoute, async (route) => {
    completeAttempts += 1;
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    return route.abort("failed");
  });
  await page.getByLabel("文件类型").selectOption("COMMERCIAL_INVOICE");
  await fileInput.setInputFiles({
    name: "commercial-invoice.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("commercial invoice e2e evidence"),
  });
  await page.getByRole("button", { name: "上传文件" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "服务暂时不可用" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "上传文件" }).click();
  await expect.poll(() => completeAttempts).toBe(1);
  await expect(
    page.getByRole("alert").filter({ hasText: "服务暂时不可用" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "上传文件" }).click();
  await expect(page.getByText("等待扫描", { exact: true })).toBeVisible();
  expect(uploadAttempts).toBe(3);
  expect(completeAttempts).toBe(1);
  await expect(page.locator(".document-card")).toHaveCount(1);
  await page.unroute(uploadRoute);
  await page.unroute(completeRoute);
  processDocumentJobs();
  await page.reload();
  await page.evaluate((token) => {
    window.localStorage.setItem("trade-workbench.access-token", token);
  }, fixture.operations_access_token);
  await expect(
    page.locator(".document-card").getByText("商业发票", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".document-card").getByText("可用", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(".document-card")
      .getByRole("button", { name: "下载", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.locator(".document-card").getByText("待审核附件", { exact: true }),
  ).toBeVisible();
  await reviewShipmentFile(page, fixture, "commercial-invoice.txt", 1);

  await page.getByLabel("文件类型").selectOption("PACKING_LIST");
  await fileInput.setInputFiles({
    name: "packing-list.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("packing list e2e evidence"),
  });
  await page.getByRole("button", { name: "上传文件" }).click();
  await expect(page.getByText("等待扫描", { exact: true })).toBeVisible();
  processDocumentJobs();
  await expect(page.getByText("离港文件已齐套")).toBeVisible();
  await page.reload();
  await page.evaluate((token) => {
    window.localStorage.setItem("trade-workbench.access-token", token);
  }, fixture.operations_access_token);
  await expect(page.getByText("离港文件已齐套")).toBeVisible();

  await reviewShipmentFile(page, fixture, "packing-list.txt", 1);

  await page
    .locator(".document-card")
    .filter({ hasText: "commercial-invoice.txt" })
    .getByRole("button", { name: "替换文件" })
    .click();
  await expect(
    page.getByText("替换 commercial-invoice.txt：将创建新版，旧版保留。"),
  ).toBeVisible();
  await fileInput.setInputFiles({
    name: "commercial-invoice-v2.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Revised commercial invoice e2e evidence"),
  });
  await verifyUploadRecovery(
    page,
    page.getByRole("button", { name: "上传文件", exact: true }),
    page.getByRole("alert").filter({ hasText: "服务暂时不可用" }),
    {
      replacement: true,
      versionNumber: 2,
      resumeFile: {
        name: "commercial-invoice-v2.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("Revised commercial invoice e2e evidence"),
      },
    },
  );
  await expect(page.getByText("等待扫描", { exact: true })).toBeVisible();
  await expect(page.getByText("第 2 版")).toBeVisible();
  processDocumentJobs();
  await expect(page.getByText("离港文件已齐套")).toBeVisible();
  await page.reload();
  await page.evaluate((token) => {
    window.localStorage.setItem("trade-workbench.access-token", token);
  }, fixture.operations_access_token);
  await expect(page.getByText("离港文件已齐套")).toBeVisible();

  const shipmentPageUrl = page.url();
  await reviewShipmentFile(page, fixture, "commercial-invoice-v2.txt", 2);
  const history = page.locator(".document-version-history").filter({
    hasText: "commercial-invoice.txt",
  });
  await history.locator("summary").click();
  await expect(
    history.getByRole("button", { name: "下载第 1 版" }),
  ).toBeVisible();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const fits = await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    );
    expect(fits).toBe(true);
    await page.screenshot({
      path: `test-results/document-history-${width}.png`,
      fullPage: true,
    });
  }
  const savedEvidence = page.waitForEvent("download");
  await history.getByRole("button", { name: "下载第 1 版" }).click();
  const downloadedEvidence = await savedEvidence;
  expect(downloadedEvidence.suggestedFilename()).toBe("commercial-invoice.txt");
  expect(await downloadedEvidence.failure()).toBeNull();
  const savedEvidencePath = await downloadedEvidence.path();
  expect(savedEvidencePath).not.toBeNull();
  expect(fs.readFileSync(savedEvidencePath!, "utf-8")).toBe(
    "commercial invoice e2e evidence",
  );
  expect(page.url()).toBe(shipmentPageUrl);
  await page.goto(shipmentPageUrl);
  await page.evaluate((token) => {
    window.localStorage.setItem("trade-workbench.access-token", token);
  }, fixture.operations_access_token);
  await expect(page.getByText("离港文件已齐套")).toBeVisible();

  await recoverShipmentDecision("ready", "确认文件齐备", "文件齐备");
  await recoverShipmentDecision("enter-customs", "进入报关", "报关中");
  await expect(page.getByText("报关中", { exact: true }).first()).toBeVisible();
  await recoverShipmentDecision("depart", "确认离港", "已离港");
  await expect(page.getByText("已离港", { exact: true }).first()).toBeVisible();
  await recoverShipmentDecision("start-transit", "开始在途运输", "运输中");
  await expect(page.getByText("运输中", { exact: true }).first()).toBeVisible();
  await recoverShipmentDecision("arrive", "确认到港", "已到港");
  await expect(page.getByText("已到港", { exact: true }).first()).toBeVisible();
  await recoverShipmentDecision("deliver", "确认完成交付", "已交付");
  await expect(page.getByText("已交付", { exact: true }).first()).toBeVisible();

  await page.goto(`/orders/${orderId}`);
  await page.evaluate((token) => {
    window.localStorage.setItem("trade-workbench.access-token", token);
  }, fixture.manager_access_token);
  await settle(balance, "E2E-BALANCE");
  await expect(page.getByRole("button", { name: "完成此待办" })).toHaveCount(2);
  for (let remaining = 2; remaining > 0; remaining--) {
    const taskForm = page
      .locator("form")
      .filter({ has: page.getByRole("button", { name: "完成此待办" }) })
      .first();
    await taskForm
      .getByLabel("处理结果")
      .fill("采购承诺、交付证据及人工批准的跟进任务均已核对完成");
    await taskForm.getByRole("button", { name: "完成此待办" }).click();
    await expect(page.getByRole("button", { name: "完成此待办" })).toHaveCount(
      remaining - 1,
    );
  }
  await expect(page.getByRole("button", { name: "完成此待办" })).toHaveCount(0);
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.operations_access_token);
  const protectedTask = page.locator("[data-work-task-id]").first();
  await expect(protectedTask).toContainText("待审核任务");
  await expect(protectedTask.getByText("任务补充信息")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "审核文本开放范围" }),
  ).toHaveCount(0);
  const reviewedTaskId = await protectedTask.getAttribute("data-work-task-id");
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  const reviewTask = page.locator(`[data-work-task-id="${reviewedTaskId}"]`);
  await reviewTask.getByRole("button", { name: "审核文本开放范围" }).click();
  await reviewTask.getByLabel("审核决定").selectOption("release");
  await reviewTask
    .getByLabel("审核说明")
    .fill("已核对任务正文和处理结果，无内部成本利润");
  await reviewTask.getByRole("checkbox").check();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await reviewTask.screenshot({
      path: `test-results/work-review-${width}.png`,
    });
  }
  await reviewTask.getByRole("button", { name: "确认文本审核" }).click();
  await expect(reviewTask.getByText("本条文本已开放。")).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.operations_access_token);
  await expect(reviewTask).not.toContainText("待审核任务");
  await reviewTask.getByText("任务补充信息", { exact: true }).click();
  await expect(
    reviewTask.getByText("采购承诺、交付证据及人工批准的跟进任务均已核对完成", {
      exact: false,
    }),
  ).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  await page.getByRole("button", { name: "检查并完成订单" }).click();
  await expect(
    page.getByText("订单已完成归档，交易与核销记录保留可追溯。"),
  ).toBeVisible();
  const orderHistory = page.getByRole("region", {
    name: "订单时间线",
    exact: true,
  });
  const historyIds: string[] = [];
  let foundCreation = false;
  for (let historyPage = 0; historyPage < 20; historyPage += 1) {
    await expect(orderHistory).toHaveAttribute("aria-busy", "false");
    await expect(
      orderHistory.locator("[data-activity-id]").first(),
    ).toBeVisible();
    historyIds.push(
      ...(await orderHistory
        .locator("[data-activity-id]")
        .evaluateAll((rows) =>
          rows.map((row) => row.getAttribute("data-activity-id")!),
        )),
    );
    if (
      await orderHistory
        .getByText("sales_order.created", { exact: true })
        .count()
    )
      foundCreation = true;
    const nextHistory = orderHistory.getByRole("button", {
      name: "下一页历史",
    });
    if (await nextHistory.isDisabled()) break;
    await nextHistory.click();
  }
  expect(historyIds.length).toBeGreaterThan(20);
  expect(new Set(historyIds).size).toBe(historyIds.length);
  expect(foundCreation).toBe(true);
  await expect(
    orderHistory.getByRole("button", { name: "下一页历史" }),
  ).toBeDisabled();
  await orderHistory.getByRole("button", { name: "刷新时间线" }).click();
  await expect(
    orderHistory.getByRole("button", { name: "上一页历史" }),
  ).toBeDisabled();
  await expect(orderHistory).toHaveAttribute("aria-busy", "false");
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            document.documentElement.scrollWidth <=
            document.documentElement.clientWidth,
        ),
      )
      .toBeTruthy();
    await page.screenshot({
      path: `test-results/finance-completed-${width}.png`,
      fullPage: true,
    });
  }

  const connectOperations = async () => {
    await page.evaluate((token) => {
      localStorage.setItem("trade-workbench.access-token", token);
      window.dispatchEvent(new Event("trade-workbench-session-change"));
    }, fixture.operations_access_token);
  };
  const recordCaseCommand = async (
    label: string,
    date?: string,
    reference?: string,
    amount?: string,
  ) => {
    await page.getByRole("button", { name: label, exact: true }).click();
    if (date) await page.getByLabel("实际发生日期").fill(date);
    if (reference) await page.getByLabel("人工申报回执号").fill(reference);
    if (amount) await page.getByLabel("实际收到退税金额").fill(amount);
    await page
      .getByRole("button", { name: `确认${label}`, exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: `确认${label}`, exact: true }),
    ).toHaveCount(0);
  };
  const uploadCaseEvidence = async (types: string[]) => {
    for (const type of types) {
      await page.getByLabel("文件类型").selectOption(type);
      const evidenceFile = {
        name: `${type}.txt`,
        mimeType: "text/plain",
        buffer: Buffer.from(`Manual ${type} evidence`),
      };
      await page.getByLabel("选择证据文件").setInputFiles(evidenceFile);
      await verifyUploadRecovery(
        page,
        page.getByRole("button", { name: "上传案件文件", exact: true }),
        page
          .getByRole("alert")
          .filter({ hasText: "操作未成功，请检查服务连接后重试。" }),
        { resumeFile: evidenceFile },
      );
      await expect(
        page.getByRole("button", { name: "上传案件文件", exact: true }),
      ).toBeEnabled();
      processDocumentJobs();
    }
    await expect(page.getByText("缺少文件：无", { exact: true })).toBeVisible({
      timeout: 15_000,
    });
  };
  await page.goto("/export/customs");
  await connectOperations();
  await page.getByText("新建报关案件", { exact: true }).click();
  await page.getByLabel("出货 ID", { exact: true }).fill(shipmentId);
  await page.getByLabel("人工申报金额", { exact: true }).fill("100.0000");
  await page.getByRole("button", { name: "创建人工跟踪案件" }).click();
  await expect(page).toHaveURL(/\/export\/customs\/[0-9a-f-]{36}$/);
  const declarationId = page.url().split("/").at(-1)!;
  await page.getByLabel("新的跟进日期").fill("2026-09-07");
  await page.getByLabel("调整原因").fill("已约定与代理核对资料");
  await page.getByRole("button", { name: "保存跟进安排" }).click();
  await expect(
    page.getByText("跟进日期：2026-09-07", { exact: true }),
  ).toBeVisible();
  await recordCaseCommand("开始准备资料");
  await uploadCaseEvidence(["COMMERCIAL_INVOICE", "PACKING_LIST"]);
  await recordCaseCommand("确认资料就绪");
  await recordCaseCommand("记录人工申报", "2026-09-05", "E2E-CUSTOMS-MANUAL");
  await recordCaseCommand("记录清关", "2026-09-06");
  await expect(page.getByText("状态：已清关", { exact: true })).toBeVisible();

  await page.goto("/export/refunds");
  await connectOperations();
  await page.getByText("新建退税案件", { exact: true }).click();
  await page.getByLabel("报关案件 ID", { exact: true }).fill(declarationId);
  await page.getByLabel("预计退税金额", { exact: true }).fill("12.3400");
  await page.getByLabel("备注", { exact: true }).fill("已与代理核对案件资料");
  await page.getByRole("button", { name: "创建人工跟踪案件" }).click();
  await expect(page).toHaveURL(/\/export\/refunds\/[0-9a-f-]{36}$/);
  await recordCaseCommand("开始准备资料");
  await uploadCaseEvidence(["COMMERCIAL_INVOICE", "BILL_OF_LADING"]);
  await recordCaseCommand("确认资料就绪");
  await recordCaseCommand("记录人工申报", "2026-09-06", "E2E-REFUND-MANUAL");
  await recordCaseCommand("记录办理中");
  await recordCaseCommand("记录收到退税", "2026-09-06", undefined, "12.0000");
  await expect(
    page.getByText("状态：已收到退税", { exact: true }),
  ).toBeVisible();
  const caseText = page.getByRole("region", { name: "案件备注审核" });
  await expect(caseText.getByText("保密内容：待审核后开放")).toBeVisible();
  await expect(caseText.getByText(/已与代理核对案件资料/)).toHaveCount(0);
  await expect(page.getByText(/回执号：E2E-REFUND-MANUAL/)).toBeVisible();
  await page.evaluate((token) => {
    localStorage.setItem("trade-workbench.access-token", token);
    window.dispatchEvent(new Event("trade-workbench-session-change"));
  }, fixture.manager_access_token);
  await caseText
    .getByRole("button", { name: "审核文本开放范围", exact: true })
    .click();
  await caseText.getByLabel("审核决定").selectOption("release");
  await caseText
    .getByLabel("审核说明")
    .fill("已核对案件全部备注与退回原因，不含成本或利润");
  await caseText.getByRole("checkbox").check();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await caseText.screenshot({
      path: `test-results/export-source-review-${width}.png`,
    });
  }
  await caseText.getByRole("button", { name: "确认文本审核" }).click();
  await expect(
    caseText.getByText("本条文本已开放。", { exact: true }),
  ).toBeVisible();
  await connectOperations();
  await expect(
    caseText.getByText("备注：已与代理核对案件资料", { exact: true }),
  ).toBeVisible();
  await expect(
    caseText.getByRole("button", { name: "审核文本开放范围" }),
  ).toHaveCount(0);
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: `test-results/refund-completed-${width}.png`,
      fullPage: true,
    });
  }
  for (const target of [
    {
      name: "purchase",
      url: orderUrl,
      region: "采购文本审核",
      hidden: "采购说明和取消正文待审核，当前不可见",
      visible: "Sanitary valve specification verified",
    },
    {
      name: "product",
      url: `/products/${productId}`,
      region: "产品说明审核",
      hidden: "产品说明待审核，当前不可见",
      visible: "Sanitary valve specification verified",
    },
    {
      name: "inquiry",
      url: `/quotations/${quotationId}`,
      region: "询盘说明审核",
      hidden: "询盘说明待审核，当前不可见",
      visible: "Two sanitary control valves",
    },
    {
      name: "quotation",
      url: `/quotations/${quotationId}`,
      region: "报价文本审核",
      hidden: "报价说明和条款待审核，当前不可见",
      visible: "30% deposit, balance before shipment",
    },
    {
      name: "order",
      url: orderUrl,
      region: "订单文本审核",
      hidden: "订单说明和条款待审核，当前不可见",
      visible: "30% deposit, balance before shipment",
    },
    {
      name: "contract",
      url: orderUrl,
      region: "合同文本审核",
      hidden: "",
      visible: "",
    },
  ]) {
    async function asRole(token: string) {
      await page.goto(target.url);
      await page.evaluate((value) => {
        localStorage.setItem("trade-workbench.access-token", value);
        window.dispatchEvent(new Event("trade-workbench-session-change"));
      }, token);
    }
    await asRole(fixture.access_token);
    if (target.hidden)
      await expect(
        page.getByText(target.hidden, { exact: true }).first(),
      ).toBeVisible();
    if (target.name === "contract") {
      await page.getByText("查看合同商业快照", { exact: true }).click();
      await expect(
        page.getByText("备注：待审核", { exact: true }),
      ).toBeVisible();
    }
    await asRole(fixture.manager_access_token);
    const section = page
      .getByRole("region", {
        name: target.region,
        exact: true,
      })
      .first();
    await section
      .getByRole("button", { name: "审核文本开放范围", exact: true })
      .first()
      .click();
    await section.getByLabel("审核决定").selectOption("release");
    await section
      .getByLabel("审核说明")
      .fill("已核对这份原文及其全部商业说明，不含成本利润");
    await section.getByRole("checkbox").check();
    for (const width of [375, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width);
      await section.screenshot({
        path: `test-results/commercial-${target.name}-review-${width}.png`,
      });
    }
    await section.getByRole("button", { name: "确认文本审核" }).click();
    await expect(
      section.getByText("本条文本已开放。", { exact: true }),
    ).toBeVisible();
    await asRole(fixture.access_token);
    if (target.visible)
      await expect(
        page.getByText(target.visible, { exact: false }).first(),
      ).toBeVisible();
    if (target.name === "contract") {
      await page.getByText("查看合同商业快照", { exact: true }).click();
      await expect(
        page.getByText("备注：Counterpart reviewed against accepted order", {
          exact: true,
        }),
      ).toBeVisible();
    }
  }
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "今天，推进哪一笔订单？" }),
  ).toBeVisible();
  await expect(page.getByText("正在读取事项…")).toHaveCount(0);
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: `test-results/overview-${width}.png`,
      fullPage: true,
    });
  }
});

for (const viewport of [
  { width: 375, height: 812 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
]) {
  test(`quotation workspace has no horizontal overflow at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("/quotations");
    await expect(
      page.getByRole("heading", { name: "报价驾驶台" }),
    ).toBeVisible();
    await page.locator('a[href^="/quotations/"]').first().click();
    await expect(page.getByRole("table", { name: /商业快照/ })).toBeVisible();
    const timeline = page.getByRole("region", {
      name: "报价时间线",
      exact: true,
    });
    await expect(timeline.getByRole("listitem").first()).toBeVisible();
    await expect(timeline).toHaveAttribute("aria-busy", "false");
    const dimensions = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
    await page.screenshot({
      path: `test-results/quotations-${viewport.width}.png`,
      fullPage: true,
    });
  });
}

for (const viewport of [
  { width: 375, height: 812 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
]) {
  test(`shipment workspace has no horizontal overflow at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("/shipments");
    await expect(
      page.getByRole("heading", { name: "出运航控台" }),
    ).toBeVisible();
    await page.locator('a[href^="/shipments/"]').first().click();
    await expect(page.getByRole("heading", { name: "本次货物" })).toBeVisible();
    await expect(page.getByText("订单快照读取中", { exact: true })).toHaveCount(
      0,
    );
    const timeline = page.getByRole("region", {
      name: "出货时间线",
      exact: true,
    });
    await expect(timeline.getByRole("listitem").first()).toBeVisible();
    await expect(timeline).toHaveAttribute("aria-busy", "false");
    const dimensions = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
    await page.screenshot({
      path: `test-results/shipments-${viewport.width}.png`,
      fullPage: true,
    });
  });
}

for (const viewport of [
  { width: 375, height: 812 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
]) {
  test(`order workspace has no horizontal overflow at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("/orders");
    await expect(
      page.getByRole("heading", { name: "订单承诺舱" }),
    ).toBeVisible();
    await page.locator('a[href^="/orders/"]').first().click();
    await expect(
      page.getByRole("table", { name: "接受版本冻结的销售订单行" }),
    ).toBeVisible();
    const timeline = page.getByRole("region", {
      name: "订单时间线",
      exact: true,
    });
    await expect(timeline.getByRole("listitem").first()).toBeVisible();
    await expect(timeline).toHaveAttribute("aria-busy", "false");
    const dimensions = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
    await page.screenshot({
      path: `test-results/orders-${viewport.width}.png`,
      fullPage: true,
    });
  });
}

test("order snapshot costs follow the current role without changing selling facts", async ({
  page,
}) => {
  await verifyOrderCostRoles(page);
});

test("quotation snapshots redact costs across live role changes", async ({
  page,
}) => {
  const fixture = loadFixture();
  const headers = {
    Authorization: `Bearer ${fixture.manager_access_token}`,
    "X-Organization-ID": fixture.organization_id,
  };
  const list = await page.request.get(
    "http://127.0.0.1:8010/api/v1/quotations",
    { headers },
  );
  expect(list.ok()).toBeTruthy();
  const id = (await list.json()).items[0].id;
  const originalResponse = await page.request.get(
    `http://127.0.0.1:8010/api/v1/quotations/${id}`,
    { headers },
  );
  expect(originalResponse.ok()).toBeTruthy();
  const original = await originalResponse.json();
  await page.goto(`/quotations/${id}`);
  for (const [role, token, visible] of [
    ["manager", fixture.manager_access_token, true],
    ["sales", fixture.access_token, false],
    ["operations", fixture.operations_access_token, false],
  ] as const) {
    const read = page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        response.url().endsWith(`/quotations/${id}`) &&
        response.status() === 200,
    );
    await page.evaluate((accessToken) => {
      localStorage.setItem("trade-workbench.access-token", accessToken);
      window.dispatchEvent(new Event("trade-workbench-session-change"));
    }, token);
    const quote = await (await read).json();
    for (let index = 0; index < quote.versions.length; index += 1) {
      const version = quote.versions[index];
      const source = original.versions[index];
      for (const field of ["total_cost", "gross_profit", "gross_margin"]) {
        expect(version[field]).toBe(visible ? source[field] : null);
      }
      expect(version.total).toBe(source.total);
      for (let line = 0; line < version.items.length; line += 1) {
        for (const field of [
          "unit_cost",
          "cost_currency",
          "cost_exchange_rate",
          "allocated_cost",
          "line_cost",
          "line_gross_profit",
        ]) {
          expect(version.items[line][field]).toBe(
            visible ? source.items[line][field] : null,
          );
        }
      }
    }
    await expect(
      page.getByRole("columnheader", { name: "成本", exact: true }),
    ).toHaveCount(visible ? 1 : 0);
    await expect(
      page.getByRole("region", { name: "收入、成本与毛利" }),
    ).toHaveCount(visible ? 1 : 0);
    for (const width of [375, 1440]) {
      await page.setViewportSize({ width, height: 950 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.locator(".quote-detail").screenshot({
        path: `test-results/quotation-cost-${role}-${width}.png`,
      });
      if (width === 375) {
        const table = page.locator(".quote-table-wrap");
        await table.evaluate((element) => {
          element.scrollLeft = element.scrollWidth;
        });
        await table.screenshot({
          path: `test-results/quotation-cost-${role}-375-amounts.png`,
        });
        await table.evaluate((element) => {
          element.scrollLeft = 0;
        });
      }
    }
  }
});
