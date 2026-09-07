import json
import os
import subprocess
import sys

import pytest
from scripts import e2e_processes


@pytest.mark.skipif(os.name != "nt", reason="Windows ownership cleanup")
def test_cleanup_rejects_stale_identity_then_stops_only_owned_process(tmp_path, monkeypatch):
    monkeypatch.setattr(e2e_processes, "ROOT", tmp_path)
    owned = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        e2e_processes.record("web", owned.pid)
        receipt = e2e_processes.receipt_path("web")
        identity = json.loads(receipt.read_text())
        identity["created"] += 1
        receipt.write_text(json.dumps(identity))
        e2e_processes.stop()
        assert owned.poll() is None
        assert unrelated.poll() is None
        e2e_processes.record("web", owned.pid)
        e2e_processes.stop()
        assert owned.wait(timeout=5) == 0
        assert unrelated.poll() is None
    finally:
        for process in (owned, unrelated):
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
