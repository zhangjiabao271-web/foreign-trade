from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from app.auth.errors import ApiProblem
from app.companies.models import Company
from app.crm.models import Lead, Opportunity
from app.export.models import CustomsDeclaration, TaxRefundCase
from app.fulfillment.models import Shipment
from app.identity.models import OrganizationMembership
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.procurement.models import PurchaseOrder
from app.sales.models import Quotation, SalesOrder
from app.work.activity_access import require_activity_subject
from app.work.models import Activity
from app.work.review import WorkReviewService, require_record
from sqlalchemy import select
from test_activity_review import SUBJECTS
from test_activity_review import seed as seed_existing
from test_document_review import reviewer
from test_purchase_receiving import confirmed_purchase
from test_shipment_documents_vertical_slice import create_shipment, executing_order
from test_work_review import decision

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)
KINDS = [*SUBJECTS, "purchase_order", "quotation", "shipment"]


def seed(f, kind):
    if kind in SUBJECTS:
        return seed_existing(f, kind)
    if kind == "purchase_order":
        owner_id = UUID(confirmed_purchase(f)["id"])
    else:
        order = executing_order(f)
        owner_id = UUID(order["quotation_id"])
        if kind == "shipment":
            shipment = create_shipment(
                f,
                [
                    {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
                    for item in order["items"]
                ],
            )
            owner_id = UUID(shipment["id"])
    with f.session_factory.begin() as session:
        activity = Activity(
            organization_id=f.organization_a,
            subject_type=kind,
            subject_id=owner_id,
            activity_type="fixture.review",
            summary="Synthetic private history",
            details={"note": "Retain original history"},
            correlation_id=uuid4(),
        )
        session.add(activity)
        session.flush()
        return owner_id, activity.id


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(session.execute(select(model.__table__).order_by(model.id)))
            for model in (
                Lead,
                Company,
                Opportunity,
                CustomsDeclaration,
                TaxRefundCase,
                PurchaseOrder,
                Quotation,
                Shipment,
                SalesOrder,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        }


@pytest.mark.parametrize("kind", KINDS)
def test_each_activity_subject_rejects_foreign_http_and_service_review(quotation_fixture, kind):
    f = quotation_fixture
    owner_id, record_id = seed(f, kind)
    subject, context = reviewer(f)
    with f.session_factory.begin() as session:
        session.add(
            OrganizationMembership(
                organization_id=f.organization_b,
                user_id=context.user_id,
                role="MANAGER",
                status="ACTIVE",
            )
        )
    foreign = replace(context, organization_id=f.organization_b)
    headers = f.headers(subject, f.organization_b) | {"Idempotency-Key": "foreign-history"}
    assert f.client.get("/api/v1/me/context", headers=headers).status_code == 200
    service = WorkReviewService(f.session_factory)
    original = service.inspect_activity(context, kind, owner_id, record_id)
    request = decision(original)
    path = f"/api/v1/work/{kind}/{owner_id}/activities/{record_id}/review"
    before = snapshot(f)
    for method in ("GET", "POST"):
        response = f.client.request(
            method,
            path,
            headers=headers,
            **({"json": request.model_dump()} if method == "POST" else {}),
        )
        assert response.status_code == 404
        assert response.json()["code"] == "WORK_CONTENT_NOT_FOUND"
        assert snapshot(f) == before
    for operation in (
        lambda: service.inspect_activity(foreign, kind, owner_id, record_id),
        lambda: service.decide_activity(
            foreign, kind, owner_id, record_id, request, key="foreign-history"
        ),
    ):
        with pytest.raises(ApiProblem) as missing:
            operation()
        assert missing.value.status == 404
        assert snapshot(f) == before
    with f.session_factory() as session:
        for operation in (
            lambda: require_activity_subject(session, foreign, kind, owner_id, lock=True),
            lambda: require_record(
                session, foreign, owner_id, "activity", record_id, subject_type=kind, lock=True
            ),
        ):
            with pytest.raises(ApiProblem) as missing:
                operation()
            assert missing.value.status == 404
    assert snapshot(f) == before
    assert service.inspect_activity(context, kind, owner_id, record_id) == original
    opened = service.decide_activity(context, kind, owner_id, record_id, request, key="own-history")
    assert opened.released and opened.details == original.details and opened.text == original.text
    after = snapshot(f)
    for table in ("activities", "audit_logs", "outbox_events", "idempotency_keys"):
        assert len(after[table]) == len(before[table]) + 1
    for table in before.keys() - {"activities", "audit_logs", "outbox_events", "idempotency_keys"}:
        assert after[table] == before[table]
    assert (
        service.decide_activity(context, kind, owner_id, record_id, request, key="own-history")
        == opened
    )
    assert snapshot(f) == after
