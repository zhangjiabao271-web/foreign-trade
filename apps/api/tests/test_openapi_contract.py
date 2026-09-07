import json
from pathlib import Path

from app.main import app

OPENAPI_SNAPSHOT = Path(__file__).parents[3] / "packages" / "api-client" / "openapi.json"


def test_fastapi_schema_matches_committed_snapshot() -> None:
    expected = json.loads(OPENAPI_SNAPSHOT.read_text(encoding="utf-8"))

    assert app.openapi() == expected
