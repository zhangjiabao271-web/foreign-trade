import pytest
from app.ai.models import AiDisclosure, AiRun, AiToolCall, ApprovalRequest
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.sales.models import SalesOrder, SalesOrderItem
from app.work.models import Activity, Task
from sqlalchemy import event, select
from test_ai_disclosure import (
    SAFE,
    decision,
    headers,
    inspect_review,
    post,
    prepare,
    submit,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: [
                dict(row)
                for row in session.execute(select(model.__table__).order_by(model.id)).mappings()
            ]
            for model in (
                AiRun,
                AiToolCall,
                AiDisclosure,
                ApprovalRequest,
                Task,
                SalesOrder,
                SalesOrderItem,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        }


@pytest.mark.parametrize("action", ["revise", "release", "restrict"])
@pytest.mark.parametrize("evidence_model", [Activity, AuditLog, OutboxEvent])
def test_content_changes_rollback_every_row_and_never_execute_tasks(
    quotation_fixture, action, evidence_model
):
    f = quotation_fixture
    run = prepare(f)
    original = inspect_review(f, submit(f, run))
    # Use a reviewed-safe candidate before testing release/restriction or a further revision.
    revision = post(
        f,
        f"/api/v1/ai/disclosures/{original['id']}/revise",
        {
            "expected_version": original["version"],
            "content_digest": original["content_digest"],
            "candidate": SAFE,
        },
        subject="quotation-manager",
    )
    assert revision.status_code == 201, revision.text
    current = revision.json()
    if action in {"restrict", "revise"}:
        released = decision(f, current)
        assert released.status_code == 200, released.text
        current = released.json()
    path = f"/api/v1/ai/disclosures/{current['id']}/decide"
    body = {
        "expected_version": current["version"],
        "content_digest": current["content_digest"],
        "confirmed": True,
        "release": action == "release",
        "reason": "Synthetic content-only decision",
    }
    if action == "revise":
        path = f"/api/v1/ai/disclosures/{current['id']}/revise"
        body = {
            "expected_version": current["version"],
            "content_digest": current["content_digest"],
            "candidate": {**SAFE, "draft": "Further safe pending revision"},
        }
    run_path = f"/api/v1/ai/runs/{run['id']}"
    visible_before = f.client.get(run_path, headers=headers(f)).json()
    before = snapshot(f)
    inserted = []

    def fail_after_insert(mapper, connection, target):
        inserted.append(target.id)
        raise RuntimeError("Injected persisted disclosure evidence failure")

    event.listen(evidence_model, "after_insert", fail_after_insert)
    try:
        with pytest.raises(RuntimeError, match="Injected persisted disclosure evidence failure"):
            post(f, path, body, subject="quotation-manager", key="content-retry")
    finally:
        event.remove(evidence_model, "after_insert", fail_after_insert)
    assert len(inserted) == 1
    assert snapshot(f) == before
    assert f.client.get(run_path, headers=headers(f)).json() == visible_before

    result = post(f, path, body, subject="quotation-manager", key="content-retry")
    assert result.status_code == (201 if action == "revise" else 200), result.text
    after = snapshot(f)
    for model in (AiRun, AiToolCall, ApprovalRequest, Task, SalesOrder, SalesOrderItem):
        assert after[model.__tablename__] == before[model.__tablename__]
    for model in (Activity, AuditLog, OutboxEvent, IdempotencyKey):
        table = model.__tablename__
        assert len(after[table]) == len(before[table]) + 1
    if action == "revise":
        assert len(after["ai_disclosures"]) == len(before["ai_disclosures"]) + 1
        prior_ids = {row["id"] for row in before["ai_disclosures"]}
        assert [row for row in after["ai_disclosures"] if row["id"] in prior_ids] == before[
            "ai_disclosures"
        ]
        assert result.json()["status"] == "PENDING"
    else:
        assert len(after["ai_disclosures"]) == len(before["ai_disclosures"])
        assert result.json()["status"] == ("APPROVED" if action == "release" else "REJECTED")
    visible = f.client.get(run_path, headers=headers(f)).json()
    assert visible["output"] == ({"artifact": SAFE} if action == "release" else None)
    assert visible["estimated_cost_usd"] is visible["input_summary"] is None
    assert visible["references"] == []
    replay = post(f, path, body, subject="quotation-manager", key="content-retry")
    assert replay.status_code == result.status_code
    assert replay.json() == result.json()
    assert snapshot(f) == after
