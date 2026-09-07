import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);
const fixturePath = path.join(root, "test-results", "e2e-fixture.json");

export default function globalTeardown() {
  const python = path.join(
    root,
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  try {
    execFileSync(python, ["apps/api/scripts/e2e_processes.py"], {
      cwd: root,
      stdio: "inherit",
      timeout: 40_000,
    });
    execFileSync(python, ["apps/api/scripts/e2e_fixture.py", "teardown"], {
      cwd: root,
      stdio: "inherit",
    });
  } finally {
    fs.rmSync(fixturePath, { force: true });
  }
}
