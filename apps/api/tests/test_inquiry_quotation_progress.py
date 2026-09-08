from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.inquiries.models import Inquiry
from app.inquiries.quotation_progress import record_quotation_created
from app.platform.models import IdempotencyKey
from sqlalchemy import func, select
from test_document_review import reviewer
from test_quotation_vertical_slice import create_commercial_inputs, post_ok, table_counts

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def snapshot(f, inquiry_id):
    with f.session_factory() as session:
        row = dict(
            session.execute(select(Inquiry.__table__).where(Inquiry.id == inquiry_id))
            .mappings()
            .one()
        )
        keys = session.scalar(select(func.count()).select_from(IdempotencyKey))
    return row, table_counts(f), keys


def test_inquiry_owned_port_checks_authority_tenant_and_caller_transaction(quotation_fixture):
    f = quotation_fixture
    request, _, _ = create_commercial_inputs(f)
    inquiry_id = UUID(request["inquiry_id"])
    _, context = reviewer(f)
    before = snapshot(f, inquiry_id)
    for actor, status in (
        (replace(context, permissions=context.permissions - {Permission.QUOTATION_WRITE}), 403),
        (replace(context, organization_id=f.organization_b), 404),
    ):
        with pytest.raises(ApiProblem) as error, f.session_factory.begin() as session:
            record_quotation_created(session, actor, inquiry_id)
        assert error.value.status == status
        assert snapshot(f, inquiry_id) == before
    with pytest.raises(RuntimeError, match="caller failed"), f.session_factory.begin() as session:
        record_quotation_created(session, context, inquiry_id)
        session.flush()
        raise RuntimeError("caller failed")
    assert snapshot(f, inquiry_id) == before


def test_closed_inquiry_cannot_be_reopened_by_quotation(quotation_fixture):
    f = quotation_fixture
    request, _, _ = create_commercial_inputs(f)
    inquiry_id = UUID(request["inquiry_id"])
    with f.session_factory.begin() as session:
        session.get(Inquiry, inquiry_id).status = "CLOSED"
    before = snapshot(f, inquiry_id)
    response = f.client.post(
        "/api/v1/quotations",
        json=request,
        headers=f.headers("quotation-manager", f.organization_a)
        | {"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"
    assert snapshot(f, inquiry_id) == before
    assert (
        f.client.get(
            "/api/v1/quotations", headers=f.headers("quotation-manager", f.organization_a)
        ).json()["items"]
        == []
    )


def test_quotation_uses_owned_port_and_rolls_it_back_on_failure(quotation_fixture, monkeypatch):
    import app.sales.services as sales

    f = quotation_fixture
    request, _, _ = create_commercial_inputs(f)
    inquiry_id = UUID(request["inquiry_id"])
    before = snapshot(f, inquiry_id)
    called = []

    def failing(session, context, record_id):
        record_quotation_created(session, context, record_id)
        called.append(record_id)
        session.flush()
        raise RuntimeError("after owned port")

    with monkeypatch.context() as patch:
        patch.setattr(sales, "record_quotation_created", failing)
        with pytest.raises(RuntimeError, match="after owned port"):
            post_ok(f, "/api/v1/quotations", "quotation-manager", request, 201)
    assert called == [inquiry_id]
    assert snapshot(f, inquiry_id) == before
    post_ok(f, "/api/v1/quotations", "quotation-manager", request, 201)
    row, _, _ = snapshot(f, inquiry_id)
    assert row["status"] == "QUOTING" and row["version"] == before[0]["version"] + 1
    assert row["description"] == before[0]["description"]
