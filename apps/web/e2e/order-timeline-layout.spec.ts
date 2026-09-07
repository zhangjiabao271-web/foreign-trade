import { expect, test } from "@playwright/test";
import fs from "node:fs";

test("long order event text wraps inside a narrow timeline", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 950 });
  await page.setContent(`
    <main style="width:245px; margin:0 auto">
      <section class="finance-section">
        <ol class="finance-timeline">
          <li><p>supplier_payment_allocation.reversed</p></li>
          <li><p>${"historical-reference-".repeat(12)}</p></li>
        </ol>
      </section>
    </main>
  `);
  await page.addStyleTag({
    content: fs.readFileSync(
      new URL("../app/globals.css", import.meta.url),
      "utf-8",
    ),
  });
  const bounds = await page
    .locator(".finance-timeline")
    .evaluate((element) => ({
      width: element.clientWidth,
      scrollWidth: element.scrollWidth,
      pageWidth: document.documentElement.clientWidth,
      pageScrollWidth: document.documentElement.scrollWidth,
    }));
  expect(bounds.scrollWidth).toBeLessThanOrEqual(bounds.width);
  expect(bounds.pageScrollWidth).toBeLessThanOrEqual(bounds.pageWidth);
});
