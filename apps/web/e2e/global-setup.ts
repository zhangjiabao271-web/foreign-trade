import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);
const fixturePath = path.join(root, "test-results", "e2e-fixture.json");

export default function globalSetup() {
  const python = path.join(
    root,
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  execFileSync(python, ["apps/api/scripts/e2e_fixture.py", "setup"], {
    cwd: root,
    stdio: "inherit",
    env: { ...process.env, E2E_FIXTURE_PATH: fixturePath },
  });
}
