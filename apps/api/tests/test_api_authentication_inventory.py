from uuid import uuid4

import pytest
from app.auth.dependencies import get_database_session, get_session_factory
from app.auth.tokens import LocalTestTokenVerifier
from app.main import app
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient

BUSINESS_ROUTES = [
    (method, route)
    for route in iter_route_contexts(app.routes)
    if isinstance(route.original_route, APIRoute) and route.path.startswith("/api/v1/")
    for method in sorted(route.methods)
]


def test_business_route_inventory_has_only_explicit_public_health_exceptions():
    public = {
        (method, route.path)
        for route in iter_route_contexts(app.routes)
        if isinstance(route.original_route, APIRoute) and not route.path.startswith("/api/v1/")
        for method in route.methods
    }
    assert public == {("GET", "/health/live"), ("GET", "/health/ready")}
    assert len(BUSINESS_ROUTES) > 100  # Prevent a broken inventory from silently passing.
    assert len({(method, route.path) for method, route in BUSINESS_ROUTES}) == len(BUSINESS_ROUTES)


@pytest.fixture
def guarded_client(monkeypatch):
    class NoDatabase:
        def __getattr__(self, name):
            raise AssertionError(f"Unauthenticated request reached database method {name}")

    def database_session():
        yield NoDatabase()

    def forbidden_factory():
        raise AssertionError("Unauthenticated request opened a command transaction")

    verifier = LocalTestTokenVerifier(
        secret="route-inventory-synthetic-secret-at-least-32-characters",
        issuer="https://route-inventory.test",
        audience="route-inventory",
    )
    monkeypatch.setitem(app.dependency_overrides, get_database_session, database_session)
    monkeypatch.setitem(app.dependency_overrides, get_session_factory, lambda: forbidden_factory)
    monkeypatch.setattr(app.state, "token_verifier", verifier, raising=False)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    "method,route",
    BUSINESS_ROUTES,
    ids=[f"{method} {route.path}" for method, route in BUSINESS_ROUTES],
)
@pytest.mark.parametrize("invalid_token", [False, True], ids=["anonymous", "invalid-token"])
def test_every_business_operation_rejects_unauthenticated_access(
    guarded_client, method, route, invalid_token
):
    path = route.path
    for name in route.param_convertors:
        path = path.replace(f"{{{name}}}", str(uuid4()))
    headers = {"X-Organization-ID": str(uuid4()), "Idempotency-Key": "route-auth-probe"}
    if invalid_token:
        headers["Authorization"] = "Bearer invalid-test-token"
    response = guarded_client.request(method, path, headers=headers)
    assert response.status_code == 401, response.text
    assert response.json()["code"] == (
        "INVALID_TOKEN" if invalid_token else "AUTHENTICATION_REQUIRED"
    )
