from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


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


def problem_response(request: Request, problem: ApiProblem) -> JSONResponse:
    request_id = str(request.state.request_id)
    problem_type = problem.code.lower().replace("_", "-")
    details = ProblemDetails(
        type=f"https://trade-workbench.local/problems/{problem_type}",
        title=problem.title,
        status=problem.status,
        code=problem.code,
        detail=problem.detail,
        request_id=request_id,
        errors=[],
    )
    return JSONResponse(
        status_code=problem.status,
        media_type="application/problem+json",
        content=details.model_dump(mode="json"),
        headers={"X-Request-ID": request_id},
    )


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ProblemDetails} for status in (400, 401, 403, 404, 409, 422, 429)
}
