// Test-only preload: simulate stale canonical bytes without modifying repository files.
import fs from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const targets = { schema: "openapi.json", types: "src/schema.d.ts" };
const relativeTarget = targets[process.env.TRADE_DRIFT_PROBE];
if (!relativeTarget) throw new Error("Unknown drift probe target");
const target = path.join(packageRoot, relativeTarget);
const originalRead = fs.readFileSync;
fs.readFileSync = function (file, ...options) {
  const result = originalRead.call(fs, file, ...options);
  if (typeof file !== "string" || path.resolve(file) !== target) return result;
  return Buffer.isBuffer(result)
    ? Buffer.concat([result, Buffer.from("\n")])
    : `${result}\n`;
};
syncBuiltinESMExports();
