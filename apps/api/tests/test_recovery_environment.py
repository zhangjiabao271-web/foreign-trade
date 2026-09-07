import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from recovery_environment import recovery_mode  # noqa: E402


@pytest.fixture
def recovery_env(monkeypatch):
    values = {
        "E2E_COMMERCIAL_RECOVERY": "1",
        "TEST_DATABASE_ADMIN_URL": (
            "postgresql+psycopg://rehearsal:local-isolated-rehearsal-only@127.0.0.1:25432/postgres"
        ),
        "MINIO_HOST": "127.0.0.1",
        "MINIO_PORT": "29000",
        "MINIO_PUBLIC_ENDPOINT": "127.0.0.1:29000",
        "MINIO_SECURE": "false",
        "MINIO_PUBLIC_SECURE": "false",
        "MINIO_ACCESS_KEY": "rehearsal",
        "MINIO_SECRET_KEY": "local-isolated-rehearsal-only",
        "MINIO_BUCKET": "trade-commercial-recovery",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_default_does_not_retain(monkeypatch):
    monkeypatch.delenv("E2E_COMMERCIAL_RECOVERY", raising=False)
    assert not recovery_mode()


def test_exact_recovery_environment(recovery_env):
    assert recovery_mode()


@pytest.mark.parametrize(
    "key,value",
    [
        ("E2E_COMMERCIAL_RECOVERY", "true"),
        ("TEST_DATABASE_ADMIN_URL", "postgresql+psycopg://rehearsal:x@127.0.0.1:5432/postgres"),
        ("MINIO_HOST", "localhost"),
        ("MINIO_PORT", "9000"),
        ("MINIO_PUBLIC_ENDPOINT", "localhost:9000"),
        ("MINIO_BUCKET", "trade-workbench-documents"),
        ("MINIO_ACCESS_KEY", "localminio"),
    ],
)
def test_recovery_refuses_other_targets(recovery_env, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises((RuntimeError, ValueError)):
        recovery_mode()
