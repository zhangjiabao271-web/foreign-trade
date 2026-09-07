import os
import shutil
import subprocess

from e2e_processes import ROOT, record


def main() -> None:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required")
    web = ROOT / "apps" / "web"
    process = subprocess.Popen(
        [
            node,
            str(web / "node_modules" / "next" / "dist" / "bin" / "next"),
            "dev",
            "--hostname",
            "127.0.0.1",
            "--port",
            "3100",
        ],
        cwd=web,
        env=os.environ.copy(),
    )
    record("web", process.pid)
    raise SystemExit(process.wait())


if __name__ == "__main__":
    main()
