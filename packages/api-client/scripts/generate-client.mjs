import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(packageRoot, "..", "..");
const checkOnly = process.argv.includes("--check");
const temporaryDirectory = checkOnly
  ? mkdtempSync(join(tmpdir(), "trade-workbench-openapi-"))
  : null;
const schemaPath = temporaryDirectory
  ? join(temporaryDirectory, "openapi.json")
  : join(packageRoot, "openapi.json");
const typesPath = temporaryDirectory
  ? join(temporaryDirectory, "schema.d.ts")
  : join(packageRoot, "src", "schema.d.ts");
const generatorPath = join(
  packageRoot,
  "node_modules",
  "openapi-typescript",
  "bin",
  "cli.js",
);

function run(command, args) {
  execFileSync(command, args, { cwd: repositoryRoot, stdio: "inherit" });
}

function assertMatches(generatedPath, canonicalPath) {
  if (!readFileSync(generatedPath).equals(readFileSync(canonicalPath))) {
    throw new Error(
      `Generated API artifact has drifted: ${canonicalPath}. Run pnpm api-client:generate.`,
    );
  }
}

try {
  run("uv", [
    "--cache-dir",
    ".uv-cache",
    "run",
    "python",
    "apps/api/scripts/export_openapi.py",
    schemaPath,
  ]);
  run(process.execPath, [generatorPath, schemaPath, "-o", typesPath]);

  if (checkOnly) {
    assertMatches(schemaPath, join(packageRoot, "openapi.json"));
    assertMatches(typesPath, join(packageRoot, "src", "schema.d.ts"));
  }
} finally {
  if (temporaryDirectory) {
    rmSync(temporaryDirectory, { recursive: true, force: true });
  }
}
