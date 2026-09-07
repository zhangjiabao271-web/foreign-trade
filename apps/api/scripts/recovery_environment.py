"""Safety boundary for the opt-in, retained synthetic browser recovery database."""

import os

from sqlalchemy.engine import make_url


def recovery_mode() -> bool:
    flag = os.getenv("E2E_COMMERCIAL_RECOVERY", "0")
    if flag == "0":
        return False
    if flag != "1":
        raise RuntimeError("E2E_COMMERCIAL_RECOVERY must be0 or1")
    admin = make_url(os.environ.get("TEST_DATABASE_ADMIN_URL", ""))
    if (
        admin.drivername != "postgresql+psycopg"
        or admin.host != "127.0.0.1"
        or admin.port != 25432
        or admin.database != "postgres"
        or admin.username != "rehearsal"
        or admin.password != "local-isolated-rehearsal-only"
    ):
        raise RuntimeError("Recovery fixture requires the dedicated isolated PostgreSQL endpoint")
    expected = {
        "MINIO_HOST": "127.0.0.1",
        "MINIO_PORT": "29000",
        "MINIO_PUBLIC_ENDPOINT": "127.0.0.1:29000",
        "MINIO_SECURE": "false",
        "MINIO_PUBLIC_SECURE": "false",
        "MINIO_ACCESS_KEY": "rehearsal",
        "MINIO_SECRET_KEY": "local-isolated-rehearsal-only",
        "MINIO_BUCKET": "trade-commercial-recovery",
    }
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Recovery fixture requires the dedicated isolated object store")
    return True
