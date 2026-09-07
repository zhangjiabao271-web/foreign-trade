from collections.abc import AsyncIterator

import app.main as main_module
import httpx
import pytest
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.mark.anyio
async def test_liveness_does_not_require_dependencies(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"service": "api", "status": "alive"}


@pytest.mark.anyio
async def test_readiness_reports_degraded_dependency(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_check_dependencies(_: object) -> dict[str, bool]:
        return {"postgres": True, "redis": False, "minio": True}

    monkeypatch.setattr(main_module, "check_dependencies", fake_check_dependencies)
    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "service": "api",
        "status": "degraded",
        "dependencies": {"postgres": True, "redis": False, "minio": True},
    }


@pytest.mark.anyio
async def test_readiness_reports_ready(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_check_dependencies(_: object) -> dict[str, bool]:
        return {"postgres": True, "redis": True, "minio": True}

    monkeypatch.setattr(main_module, "check_dependencies", fake_check_dependencies)
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
