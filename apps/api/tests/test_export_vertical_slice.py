from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.export.models import CustomsDeclaration
from app.export.schemas import (
    CaseCommand,
    CustomsClear,
    CustomsCreate,
    ManualSubmission,
    RefundCreate,
    RefundReceived,
)
from app.export.services import ExportCommandService
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_shipment_documents_vertical_slice import (
    create_shipment,
    executing_order,
    upload_required_document,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")


def test_manual_customs_to_partial_final_refund_requires_available_evidence(
    quotation_fixture, fake_storage
):
    f = quotation_fixture
    order = executing_order(f)
    shipment = create_shipment(
        f,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    )
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    service = ExportCommandService(f.session_factory)
    request = CustomsCreate(
        shipment_id=UUID(shipment["id"]),
        declared_amount=Decimal(order["total"]),
        currency_code=order["currency_code"],
    )
    declaration, missing = service.create_customs(context, request, key="customs-once")
    assert missing == ["COMMERCIAL_INVOICE", "PACKING_LIST"]
    assert service.create_customs(context, request, key="customs-once")[0].id == declaration.id
    declaration, _ = service.customs_command(
        context, declaration.id, "prepare", CaseCommand(expected_version=declaration.version)
    )
    with pytest.raises(ApiProblem) as blocked:
        service.customs_command(
            context, declaration.id, "ready", CaseCommand(expected_version=declaration.version)
        )
    assert blocked.value.code == "EXPORT_DOCUMENTS_INCOMPLETE"
    for document_type in missing:
        upload_required_document(
            f,
            fake_storage,
            shipment_id=str(declaration.id),
            document_type=document_type,
            target_type="CUSTOMS_DECLARATION",
        )
    declaration, missing = service.customs_command(
        context, declaration.id, "ready", CaseCommand(expected_version=declaration.version)
    )
    assert missing == []
    declaration, _ = service.customs_command(
        context,
        declaration.id,
        "submit",
        ManualSubmission(
            expected_version=declaration.version,
            external_reference="MANUAL-CUSTOMS-01",
            occurred_on=date(2026, 9, 5),
        ),
    )
    declaration, _ = service.customs_command(
        context,
        declaration.id,
        "clear",
        CustomsClear(expected_version=declaration.version, occurred_on=date(2026, 9, 6)),
    )
    assert declaration.status == "CLEARED"
    refund, missing = service.create_refund(
        context,
        RefundCreate(customs_declaration_id=declaration.id, expected_amount=Decimal("12.3400")),
        key="refund-once",
    )
    refund, _ = service.refund_command(
        context, refund.id, "prepare", CaseCommand(expected_version=refund.version)
    )
    for document_type in missing:
        upload_required_document(
            f,
            fake_storage,
            shipment_id=str(refund.id),
            document_type=document_type,
            target_type="TAX_REFUND_CASE",
        )
    refund, missing = service.refund_command(
        context, refund.id, "ready", CaseCommand(expected_version=refund.version)
    )
    assert missing == []
    refund, _ = service.refund_command(
        context,
        refund.id,
        "submit",
        ManualSubmission(
            expected_version=refund.version,
            external_reference="MANUAL-REFUND-01",
            occurred_on=date(2026, 9, 7),
        ),
    )
    refund, _ = service.refund_command(
        context, refund.id, "process", CaseCommand(expected_version=refund.version)
    )
    with pytest.raises(ApiProblem) as too_large:
        service.refund_command(
            context,
            refund.id,
            "receive",
            RefundReceived(
                expected_version=refund.version,
                occurred_on=date(2026, 9, 8),
                refunded_amount=Decimal("13"),
            ),
        )
    assert too_large.value.code == "REFUND_AMOUNT_EXCEEDED"
    refund, _ = service.refund_command(
        context,
        refund.id,
        "receive",
        RefundReceived(
            expected_version=refund.version,
            occurred_on=date(2026, 9, 8),
            refunded_amount=Decimal("12"),
        ),
    )
    assert refund.status == "REFUNDED"
    assert refund.expected_amount - refund.refunded_amount == Decimal("0.3400")
    headers = f.headers("quotation-manager", f.organization_a)
    for path, record_id, field, expected in (
        ("customs-declarations", declaration.id, "cleared_on", "2026-09-06"),
        ("tax-refund-cases", refund.id, "refunded_on", "2026-09-08"),
    ):
        response = f.client.get(f"/api/v1/{path}/{record_id}/activities", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["items"][0]["details"][field] == expected
        protected = f.client.get(
            f"/api/v1/{path}/{record_id}/activities",
            headers=f.headers("quotation-operations", f.organization_a),
        )
        assert protected.status_code == 200
        assert protected.json()["items"][0]["details"] == {}
        assert protected.json()["items"][0]["summary"] is None


def test_export_http_contract_requires_permissions_versions_and_tenant_owned_cursor(
    quotation_fixture,
):
    f = quotation_fixture
    order = executing_order(f)
    shipment = create_shipment(
        f,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    )
    request = {
        "shipment_id": shipment["id"],
        "declared_amount": order["total"],
        "currency_code": order["currency_code"],
    }
    sales = f.headers("quotation-sales", f.organization_a)
    operations = {
        **f.headers("quotation-operations", f.organization_a),
        "Idempotency-Key": "customs-api",
    }
    assert (
        f.client.post("/api/v1/customs-declarations", headers=sales, json=request).status_code
        == 403
    )
    created = f.client.post("/api/v1/customs-declarations", headers=operations, json=request)
    assert created.status_code == 201, created.text
    case = created.json()
    assert case["missing_document_types"] == ["COMMERCIAL_INVOICE", "PACKING_LIST"]
    assert (
        f.client.post("/api/v1/customs-declarations", headers=operations, json=request).json()
        == case
    )
    other = f.headers("quotation-other", f.organization_b)
    assert (
        f.client.get(f"/api/v1/customs-declarations/{case['id']}", headers=other).status_code == 404
    )
    assert f.client.get("/api/v1/customs-declarations", headers=other).json() == {
        "items": [],
        "next_cursor": None,
        "has_more": False,
    }
    assert (
        f.client.get(f"/api/v1/customs-declarations?cursor={case['id']}", headers=other).status_code
        == 404
    )
    stale = f.client.post(
        f"/api/v1/customs-declarations/{case['id']}/prepare",
        headers=operations,
        json={"expected_version": case["version"] + 1},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"
    direct_status = f.client.post(
        f"/api/v1/customs-declarations/{case['id']}/prepare",
        headers=operations,
        json={"expected_version": case["version"], "status": "CLEARED"},
    )
    assert direct_status.status_code == 422
    prepared = f.client.post(
        f"/api/v1/customs-declarations/{case['id']}/prepare",
        headers=operations,
        json={"expected_version": case["version"]},
    )
    assert prepared.status_code == 200, prepared.text
    timeline = f"/api/v1/customs-declarations/{case['id']}/activities"
    first = f.client.get(timeline, headers=operations, params={"limit": 1}).json()
    assert first["has_more"] is True
    assert first["items"][0]["activity_type"] == "customs_declaration.documents_requested"
    second = f.client.get(
        timeline, headers=operations, params={"limit": 1, "cursor": first["next_cursor"]}
    ).json()
    assert second["has_more"] is False
    assert second["next_cursor"] is None
    assert second["items"][0]["activity_type"] == "customs_declaration.created"
    assert f.client.get(timeline, headers=other).status_code == 404
    assert f.client.get(timeline, headers=operations, params={"cursor": uuid4()}).status_code == 400
    scheduled = f.client.post(
        f"/api/v1/customs-declarations/{case['id']}/schedule-follow-up",
        headers=operations,
        json={
            "expected_version": prepared.json()["version"],
            "follow_up_date": "2026-09-07",
            "reason": "Agent follow-up scheduled",
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    assert scheduled.json()["follow_up_date"] == "2026-09-07"
    queue = f.client.get("/api/v1/overview/customs", headers=operations).json()
    assert queue["items"][0]["due_date"] == "2026-09-07"
    denied = f.client.post(
        f"/api/v1/customs-declarations/{case['id']}/schedule-follow-up",
        headers=sales,
        json={
            "expected_version": scheduled.json()["version"],
            "follow_up_date": None,
            "reason": "Clear follow-up date",
        },
    )
    assert denied.status_code == 403


@pytest.mark.parametrize("record_model", [Activity, AuditLog, OutboxEvent])
def test_export_creation_rolls_back_each_required_record(quotation_fixture, record_model):
    f = quotation_fixture
    order = executing_order(f)
    shipment = create_shipment(
        f,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    )
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    service = ExportCommandService(f.session_factory)
    request = CustomsCreate(
        shipment_id=UUID(shipment["id"]), declared_amount=Decimal("1"), currency_code="USD"
    )

    def counts():
        with f.session_factory() as session:
            return tuple(
                session.scalar(select(func.count()).select_from(model))
                for model in (CustomsDeclaration, Activity, AuditLog, OutboxEvent)
            )

    before = counts()

    def fail(*_):
        raise RuntimeError("export atomicity failure")

    event.listen(record_model, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="export atomicity failure"):
            service.create_customs(context, request, key="atomic-create")
    finally:
        event.remove(record_model, "before_insert", fail)
    assert counts() == before
    created, _ = service.create_customs(context, request, key="atomic-create")
    assert created.declaration_number.endswith("000001")
