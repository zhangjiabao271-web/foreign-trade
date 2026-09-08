from http import HTTPStatus
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException


class ProblemDetails(BaseModel):
    type: str
    title: str
    status: int
    code: str
    detail: str
    request_id: str
    errors: list[dict[str, object]]


class ApiProblem(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail


def problem_response(
    request: Request,
    problem: ApiProblem,
    *,
    errors: list[dict[str, object]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = str(request.state.request_id)
    problem_type = problem.code.lower().replace("_", "-")
    details = ProblemDetails(
        type=f"https://trade-workbench.local/problems/{problem_type}",
        title=problem.title,
        status=problem.status,
        code=problem.code,
        detail=problem.detail,
        request_id=request_id,
        errors=errors or [],
    )
    return JSONResponse(
        status_code=problem.status,
        media_type="application/problem+json",
        content=details.model_dump(mode="json"),
        headers={**(headers or {}), "X-Request-ID": request_id},
    )


def validation_problem_response(request: Request, error: RequestValidationError) -> JSONResponse:
    entries: list[dict[str, object]] = []
    for item in error.errors()[:100]:
        location = item.get("loc", ())
        source = location[0] if location else "request"
        if source not in {"body", "query", "path", "header", "cookie"}:
            source = "request"
        category = {
            "missing": "REQUIRED_VALUE",
            "extra_forbidden": "UNEXPECTED_FIELD",
            "json_invalid": "INVALID_JSON",
        }.get(item.get("type", ""), "INVALID_VALUE")
        # Never expose raw input, arbitrary location segments or custom validator messages.
        entries.append({"location": source, "code": category})
    return problem_response(
        request,
        ApiProblem(
            422, "REQUEST_VALIDATION_ERROR", "Invalid request", "Check the submitted fields."
        ),
        errors=entries,
    )


def http_problem_response(request: Request, error: HTTPException) -> JSONResponse:
    try:
        title = HTTPStatus(error.status_code).phrase
    except ValueError:
        title = "HTTP error"
    headers = {
        key: value
        for key, value in (error.headers or {}).items()
        if key.lower() in {"allow", "www-authenticate", "retry-after"}
    }
    return problem_response(
        request,
        ApiProblem(error.status_code, f"HTTP_{error.status_code}", title, title),
        headers=headers,
    )


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ProblemDetails} for status in (400, 401, 403, 404, 409, 422, 429)
}
