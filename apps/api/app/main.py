from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Literal

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint

from app.ai.routers import router as ai_router
from app.auth.dependencies import assign_request_id
from app.auth.errors import (
    PROBLEM_RESPONSES,
    ApiProblem,
    http_problem_response,
    problem_response,
    validation_problem_response,
)
from app.auth.routers import router as auth_router
from app.catalog.routers import router as products_router
from app.catalog.supplier_routers import router as supplier_links_router
from app.catalog.text_routers import router as product_text_router
from app.companies.archive_routers import router as company_archive_router
from app.companies.routers import router as companies_router
from app.core.config import get_settings
from app.core.health import check_dependencies
from app.core.observability import (
    Observation,
    configure_safe_logging,
    observe,
    observe_pool,
    request_metrics,
)
from app.crm.opportunity_routers import router as opportunities_router
from app.crm.routers import router as leads_router
from app.crm.text_routers import router as crm_text_router
from app.documents.routers import router as documents_router
from app.export.routers import router as export_router
from app.export.text_routers import router as export_text_router
from app.finance.expense_routers import router as expenses_router
from app.finance.funding_routers import router as funding_router
from app.finance.routers import router as finance_router
from app.finance.supplier_routers import router as supplier_finance_router
from app.fulfillment.routers import router as shipments_router
from app.identity.administration_routers import router as administration_router
from app.inquiries.routers import router as inquiries_router
from app.inquiries.text_routers import router as inquiry_text_router
from app.platform.operations_routers import router as operations_router
from app.platform.outbox_router import router as outbox_router
from app.platform.routers import router as jobs_router
from app.procurement.routers import router as purchase_orders_router
from app.procurement.text_routers import router as purchase_text_router
from app.sales.contract_routers import router as sales_contracts_router
from app.sales.order_routers import router as sales_orders_router
from app.sales.routers import router as quotations_router
from app.sales.text_routers import router as commercial_text_router
from app.work.activity_routers import router as activity_review_router
from app.work.overview import router as overview_router
from app.work.routers import router as work_router


class LivenessResponse(BaseModel):
    service: Literal["api"] = "api"
    status: Literal["alive"] = "alive"


class ReadinessResponse(BaseModel):
    service: Literal["api"] = "api"
    status: Literal["ready", "degraded"]
    dependencies: dict[str, bool]


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    configure_safe_logging()
    observe(Observation(event="service.started", service="api"))
    yield


app = FastAPI(
    title="Trade Workbench API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
    responses=PROBLEM_RESPONSES,
)
app.include_router(auth_router)
app.include_router(administration_router)
app.include_router(jobs_router)
app.include_router(outbox_router)
app.include_router(operations_router)
app.include_router(leads_router)
app.include_router(opportunities_router)
app.include_router(companies_router)
app.include_router(company_archive_router)
app.include_router(products_router)
app.include_router(supplier_links_router)
app.include_router(inquiries_router)
app.include_router(quotations_router)
app.include_router(sales_orders_router)
app.include_router(sales_contracts_router)
app.include_router(purchase_orders_router)
app.include_router(purchase_text_router)
app.include_router(shipments_router)
app.include_router(documents_router)
app.include_router(finance_router)
app.include_router(expenses_router)
app.include_router(funding_router)
app.include_router(supplier_finance_router)
app.include_router(work_router)
app.include_router(crm_text_router)
app.include_router(product_text_router)
app.include_router(inquiry_text_router)
app.include_router(commercial_text_router)
app.include_router(activity_review_router)
app.include_router(export_router)
app.include_router(export_text_router)
app.include_router(overview_router)
app.include_router(ai_router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    request.state.request_id = assign_request_id(request)
    started = perf_counter()
    response_status = 500
    try:
        response = await call_next(request)
        response_status = response.status_code
        response.headers["X-Request-ID"] = str(request.state.request_id)
        return response
    finally:
        elapsed = (perf_counter() - started) * 1000
        route = getattr(request.scope.get("route"), "path", "<unmatched>")
        organization_id = getattr(request.state, "verified_organization_id", None)
        method = (
            request.method
            if request.method in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
            else "OTHER"
        )
        observe(
            Observation(
                event="api.request",
                service="api",
                request_id=request.state.request_id,
                organization_id=organization_id,
                route=route,
                method=method,
                status=response_status,
                duration_ms=round(elapsed, 3),
            )
        )
        if organization_id is not None:
            try:
                request_metrics.record(
                    organization_id,
                    status=response_status,
                    duration_ms=elapsed,
                    upload=method == "POST" and route.startswith("/api/v1/documents"),
                )
                observe_pool(request.state.database_engine, "api")
            except Exception:
                pass  # Telemetry is best effort; never invalidate a committed command result.


@app.exception_handler(ApiProblem)
async def api_problem_handler(request: Request, problem: ApiProblem) -> Response:
    return problem_response(request, problem)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, error: RequestValidationError) -> Response:
    return validation_problem_response(request, error)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, error: HTTPException) -> Response:
    return http_problem_response(request, error)


@app.get("/health/live", response_model=LivenessResponse, tags=["health"])
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@app.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
    tags=["health"],
)
async def readiness(response: Response) -> ReadinessResponse:
    dependencies = await check_dependencies(get_settings())
    ready = all(dependencies.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ready else "degraded",
        dependencies=dependencies,
    )
