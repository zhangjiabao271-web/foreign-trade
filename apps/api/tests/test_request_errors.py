import json
from uuid import UUID, uuid4

import pytest
from app.auth.errors import http_problem_response, validation_problem_response
from app.main import app
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

pytest_plugins = ("test_quotation_vertical_slice",)


def test_unknown_route_is_a_safe_problem():
    with TestClient(app) as client:
        response = client.get("/api/v1/not-a-route-private-sentinel")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "HTTP_404"
    assert body["status"] == 404
    assert UUID(body["request_id"])
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert "private-sentinel" not in response.text


def test_method_error_preserves_allow():
    with TestClient(app) as client:
        response = client.post("/health/live")
    assert response.status_code == 405
    assert response.json()["code"] == "HTTP_405"
    assert "GET" in response.headers["Allow"]


def test_malformed_json_never_echoes_body():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/inquiries",
            content='{"private-sentinel":',
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_VALIDATION_ERROR"
    assert response.json()["errors"]
    assert "private-sentinel" not in response.text


@pytest.mark.integration
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/v1/sales-orders/not-a-uuid", None),
        ("get", "/api/v1/sales-orders?limit=private-sentinel", None),
        ("post", "/api/v1/inquiries", {"private-sentinel": "cost-private-sentinel"}),
    ],
)
def test_authenticated_invalid_inputs_have_safe_contract(quotation_fixture, method, path, body):
    f = quotation_fixture
    response = f.client.request(
        method, path, json=body, headers=f.headers("quotation-manager", f.organization_a)
    )
    assert response.status_code == 422
    result = response.json()
    assert result["code"] == "REQUEST_VALIDATION_ERROR"
    assert result["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["content-type"] == "application/problem+json"
    assert result["errors"]
    assert "private-sentinel" not in response.text
    assert "not-a-uuid" not in response.text


def test_validation_sanitizes_locations_messages_context_and_caps_entries():
    request = Request({"type": "http", "state": {"request_id": uuid4()}})
    error = RequestValidationError(
        [
            {
                "type": "private-sentinel",
                "loc": ("body", "private-sentinel", 3),
                "input": "private-sentinel",
                "msg": "private-sentinel",
                "ctx": {"error": ValueError("private-sentinel")},
            }
        ]
        * 120
    )
    response = validation_problem_response(request, error)
    result = json.loads(response.body)
    assert len(result["errors"]) == 100
    assert result["errors"][0] == {"location": "body", "code": "INVALID_VALUE"}
    assert b"private-sentinel" not in response.body


@pytest.mark.parametrize(
    "status,header,value",
    [
        (401, "WWW-Authenticate", "Bearer"),
        (429, "Retry-After", "30"),
    ],
)
def test_http_protocol_headers_survive_without_exception_details(status, header, value):
    request = Request({"type": "http", "state": {"request_id": uuid4()}})
    response = http_problem_response(
        request,
        HTTPException(
            status,
            detail={"secret": "private-sentinel"},
            headers={header: value},
        ),
    )
    assert response.status_code == status
    assert response.headers[header] == value
    assert b"private-sentinel" not in response.body


def test_all_advertised_validation_responses_use_problem_details():
    for path in app.openapi()["paths"].values():
        for operation in path.values():
            if "responses" in operation and "422" in operation["responses"]:
                schema = operation["responses"]["422"]["content"]["application/json"]["schema"]
                assert schema == {"$ref": "#/components/schemas/ProblemDetails"}
