"""Explicit paid opt-in only: synthetic PostgreSQL fixture, real provider, no external writes."""

import json
import os
from uuid import UUID, uuid4

import pytest
from app.ai.models import AiRun, AiToolCall
from app.ai.provider import configured_provider
from app.ai.runner import AiRunner
from app.core.config import Settings
from app.sales.models import SalesOrder
from sqlalchemy import select
from test_ai_copilot import create_run
from test_shipment_documents_vertical_slice import executing_order

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("ALLOW_PAID_DEEPSEEK_ACCEPTANCE") != "1",
        reason="Real DeepSeek calls require explicit paid acceptance opt-in",
    ),
]


@pytest.mark.parametrize(
    "intent,required_tool",
    [
        ("TASK_DRAFT", "read_order"),
        ("EMAIL_DRAFT", "read_order"),
        ("TIMELINE", "order_timeline"),
        ("PROFIT", "order_profit"),
        ("SEARCH", "search_companies"),
    ],
)
def test_real_deepseek_preserves_business_and_private_boundary(
    quotation_fixture, monkeypatch, intent, required_tool
):
    fixture = quotation_fixture
    settings = Settings(ai_provider="deepseek", deepseek_model="deepseek-v4-pro")
    assert settings.deepseek_api_key, "DEEPSEEK_API_KEY must be supplied through environment"
    monkeypatch.setattr("app.ai.routers.get_settings", lambda: settings)
    order = executing_order(fixture)
    actor = "quotation-manager" if intent == "PROFIT" else "quotation-sales"
    if intent == "SEARCH":
        created = fixture.client.post(
            "/api/v1/ai/runs",
            headers={
                **fixture.headers(actor, fixture.organization_a),
                "Idempotency-Key": str(uuid4()),
            },
            json={"intent": intent, "search_term": "Blue Current"},
        )
    else:
        created = create_run(fixture, order["id"], intent=intent, subject=actor)
    assert created.status_code == 202
    run_id = UUID(created.json()["id"])
    assert created.json()["model"] == "deepseek/deepseek-v4-pro"
    runner = AiRunner(fixture.session_factory, configured_provider(settings), settings)
    runner.execute(organization_id=fixture.organization_a, run_id=run_id, request_id=uuid4())
    with fixture.session_factory() as session:
        run = session.scalar(
            select(AiRun).where(AiRun.organization_id == fixture.organization_a, AiRun.id == run_id)
        )
        if run.status != "SUCCEEDED":
            failure_calls = list(
                session.scalars(
                    select(AiToolCall)
                    .where(
                        AiToolCall.organization_id == fixture.organization_a,
                        AiToolCall.run_id == run_id,
                    )
                    .order_by(AiToolCall.created_at, AiToolCall.id)
                )
            )
            print(
                json.dumps(
                    {
                        "live_failure": intent,
                        "code": run.error_code,
                        "input_tokens": run.input_tokens,
                        "output_tokens": run.output_tokens,
                        "calls": [
                            {"tool": call.tool_name, "status": call.status, "code": call.error_code}
                            for call in failure_calls
                        ],
                    }
                )
            )
        assert run.status == "SUCCEEDED", run.error_code
        assert run.output["executed_actions"] == []
        if intent == "TASK_DRAFT":
            assert run.output["artifact"]["task_title"]
        else:
            assert run.output["artifact"]["task_title"] is None
        assert run.output["artifact"]["draft"]
        assert run.references
        assert run.input_tokens > 0 and run.output_tokens > 0
        calls = list(
            session.scalars(
                select(AiToolCall).where(
                    AiToolCall.organization_id == fixture.organization_a,
                    AiToolCall.run_id == run_id,
                )
            )
        )
        assert calls and all(
            call.status == "SUCCEEDED"
            or (call.status == "DENIED" and call.error_code == "AI_TOOL_LIMIT_EXCEEDED")
            for call in calls
        )
        assert any(call.tool_name == required_tool and call.status == "SUCCEEDED" for call in calls)
        current_order = session.scalar(
            select(SalesOrder).where(
                SalesOrder.organization_id == fixture.organization_a,
                SalesOrder.id == UUID(order["id"]),
            )
        )
        assert current_order.status == order["status"]
        # Synthetic artifact only; never print credentials, inputs, reasoning or provider errors.
        print(
            json.dumps(
                {
                    "model": run.model,
                    "intent": intent,
                    "input_tokens": run.input_tokens,
                    "output_tokens": run.output_tokens,
                    "denied_parallel_calls": sum(call.status == "DENIED" for call in calls),
                    "artifact": run.output["artifact"],
                    "facts": run.output["facts"],
                },
                ensure_ascii=True,
            )
        )
    result = fixture.client.get(
        f"/api/v1/ai/runs/{run_id}",
        headers=fixture.headers(actor, fixture.organization_a),
    ).json()
    assert result["status"] == "SUCCEEDED"
    if intent == "PROFIT":
        assert result["output"] and not result["content_protected"]
    else:
        assert result["content_protected"]
        assert result["output"] is None and result["estimated_cost_usd"] is None
    other_actor = "quotation-sales" if actor == "quotation-manager" else "quotation-manager"
    for actor, org in (
        (other_actor, fixture.organization_a),
        ("quotation-other", fixture.organization_b),
    ):
        assert (
            fixture.client.get(
                f"/api/v1/ai/runs/{run_id}", headers=fixture.headers(actor, org)
            ).status_code
            == 404
        )
