import { expect, type Locator, type Page } from "@playwright/test";

/** Commit both commands, lose each response, then recover without another completion. */
export async function verifyUploadRecovery(
  page: Page,
  button: Locator,
  error: Locator,
  options: {
    replacement?: boolean;
    versionNumber?: number;
    resumeFile?: { name: string; mimeType: string; buffer: Buffer };
  } = {},
) {
  const createRoute = options.replacement
    ? "**/api/backend/api/v1/documents/*/version-upload-sessions"
    : "**/api/backend/api/v1/documents/upload-sessions";
  const completeRoute = "**/api/backend/api/v1/documents/*/versions/*/complete";
  let attempts = 0;
  let completions = 0;
  let key: string | undefined;
  let payload: string | null;
  let documentId: string;
  let versionId: string;
  const resumeRoute =
    "**/api/backend/api/v1/documents/*/versions/*/upload-session";
  await page.route(createRoute, async (route) => {
    attempts += 1;
    const request = route.request();
    expect(request.headers()["idempotency-key"]).toBeTruthy();
    const response = await route.fetch();
    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.document.latest_version_number).toBe(
      options.versionNumber ?? 1,
    );
    if (attempts === 1) {
      key = request.headers()["idempotency-key"];
      payload = request.postData();
      documentId = body.document.id;
      versionId = body.version_id;
      return route.abort("failed");
    }
    expect(request.headers()["idempotency-key"]).toBe(key);
    expect(request.postData()).toBe(payload);
    expect(body.document.id).toBe(documentId);
    expect(body.version_id).toBe(versionId);
    if (attempts === 3) expect(body.upload_url).toBeNull();
    return route.fulfill({ response });
  });
  await page.route(completeRoute, async (route) => {
    completions += 1;
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    return options.resumeFile
      ? route.fulfill({ response })
      : route.abort("failed");
  });
  try {
    await button.click();
    await expect(error).toBeVisible();
    if (options.resumeFile) {
      // This fixture's init script resets the role on each navigation.
      const credential = await page.evaluate(() =>
        localStorage.getItem("trade-workbench.access-token"),
      );
      await page.reload();
      await page.evaluate((token) => {
        if (token) localStorage.setItem("trade-workbench.access-token", token);
        window.dispatchEvent(new Event("trade-workbench-session-change"));
      }, credential);
      const form = page.locator(
        `form[data-document-version-id="${versionId!}"]`,
      );
      const input = form.getByLabel("重新选择原文件");
      const resume = form.getByRole("button", { name: "继续上传原文件" });
      await input.setInputFiles({
        ...options.resumeFile,
        buffer: Buffer.from("wrong file content"),
      });
      await resume.click();
      await expect(form.getByRole("alert")).toContainText("文件不匹配");
      expect(completions).toBe(0);
      for (const width of [375, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        await expect
          .poll(() =>
            page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
          )
          .toBe(true);
        await form.screenshot({
          path: `test-results/resume-${options.resumeFile.name}-${width}.png`,
        });
      }
      let resumptions = 0;
      await page.route(resumeRoute, async (route) => {
        resumptions += 1;
        const response = await route.fetch();
        expect(response.status()).toBe(200);
        const body = await response.json();
        expect(body.document.id).toBe(documentId);
        expect(body.version_id).toBe(versionId);
        expect(body.document.latest_version_number).toBe(
          options.versionNumber ?? 1,
        );
        return resumptions === 1
          ? route.abort("failed")
          : route.fulfill({ response });
      });
      await input.setInputFiles(options.resumeFile);
      await resume.click();
      await expect(form.getByRole("alert")).toContainText("续传未确认成功");
      await expect(resume).toBeEnabled();
      await resume.click();
      await expect(form).toHaveCount(0);
      expect(attempts).toBe(1);
      expect(resumptions).toBe(2);
      expect(completions).toBe(1);
      return;
    }
    await expect(button).toBeEnabled();
    await button.click();
    await expect.poll(() => completions).toBe(1);
    await expect(error).toBeVisible();
    await expect(button).toBeEnabled();
    await button.click();
    await expect(error).toHaveCount(0);
    await expect(button).toBeEnabled();
    expect(attempts).toBe(3);
    expect(completions).toBe(1);
  } finally {
    if (!page.isClosed()) {
      await page.unroute(createRoute);
      await page.unroute(completeRoute);
      await page.unroute(resumeRoute);
    }
  }
}
