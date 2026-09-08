import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  cpSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
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

test("changed Pydantic response source fails the unchanged client check", () => {
  const temporary = mkdtempSync(path.join(tmpdir(), "trade-pydantic-drift-"));
  const source = path.join(root, "apps/api/app/crm/schemas.py");
  const before = [...files, source].map((file) => readFileSync(file));
  try {
    cpSync(path.join(root, "apps/api/app"), path.join(temporary, "app"), {
      recursive: true,
      filter: (file) => !file.includes("__pycache__"),
    });
    const modelPath = path.join(temporary, "app/crm/schemas.py");
    const original = readFileSync(modelPath, "utf8");
    const declaration = "class LeadResponse(BaseModel):";
    assert.equal(original.split(declaration).length, 2);
    writeFileSync(
      modelPath,
      original.replace(
        declaration,
        `${declaration}\n    drift_probe: str = \"probe\"`,
      ),
    );
    const env = { ...process.env, PYTHONPATH: temporary };
    const exported = path.join(temporary, "changed-openapi.json");
    const exportResult = spawnSync(
      "uv",
      [
        "--cache-dir",
        ".uv-cache",
        "run",
        "python",
        "apps/api/scripts/export_openapi.py",
        exported,
      ],
      { cwd: root, env, encoding: "utf8", timeout: 120_000 },
    );
    assert.ifError(exportResult.error);
    assert.equal(exportResult.status, 0, exportResult.stderr);
    const schema = JSON.parse(readFileSync(exported, "utf8"));
    assert.equal(
      schema.components.schemas.LeadResponse.properties.drift_probe.type,
      "string",
    );
    const result = spawnSync(
      process.execPath,
      [path.join(packageRoot, "scripts/generate-client.mjs"), "--check"],
      { cwd: root, env, encoding: "utf8", timeout: 120_000 },
    );
    assert.ifError(result.error);
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, /Generated API artifact has drifted:/);
    assert.ok(result.stderr.includes(files[0]));
  } finally {
    [...files, source].forEach((file, index) =>
      assert.deepEqual(readFileSync(file), before[index]),
    );
    rmSync(temporary, { recursive: true, force: true });
  }
});
