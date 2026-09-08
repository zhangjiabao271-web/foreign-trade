import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const packageRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const root = path.resolve(packageRoot, "../..");
const files = ["openapi.json", "src/schema.d.ts"].map((name) =>
  path.join(packageRoot, name),
);

for (const target of ["schema", "types"]) {
  test(`generation check rejects stale ${target} without changing artifacts`, () => {
    const before = files.map((file) => readFileSync(file));
    const result = spawnSync(
      process.execPath,
      [
        "--import",
        new URL("stale-artifact-preload.mjs", import.meta.url).href,
        path.join(packageRoot, "scripts/generate-client.mjs"),
        "--check",
      ],
      {
        cwd: root,
        env: { ...process.env, TRADE_DRIFT_PROBE: target },
        encoding: "utf8",
        timeout: 120_000,
      },
    );
    assert.ifError(result.error);
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, /Generated API artifact has drifted:/);
    assert.ok(result.stderr.includes(files[target === "schema" ? 0 : 1]));
    files.forEach((file, index) =>
      assert.deepEqual(readFileSync(file), before[index]),
    );
  });
}
