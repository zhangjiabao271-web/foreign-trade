from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.auth.errors import ApiProblem
from app.companies.models import Company, CompanyRole
from app.fulfillment.services import ShipmentCommandService
from sqlalchemy import select
from test_document_review import reviewer
from test_shipment_creation_idempotency import counts, setup
from test_shipment_parent_atomicity import snapshot

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


@pytest.mark.parametrize("state", ("foreign", "missing", "deleted", "role_missing", "active"))
def test_forwarder_requires_live_owned_company_before_role(quotation_fixture, state):
    f = quotation_fixture
    _, body = setup(f)
    _, context = reviewer(f)
    with f.session_factory.begin() as session:
        company = Company(
            organization_id=f.organization_b if state == "foreign" else f.organization_a,
            name="Synthetic forwarder",
            name_normalized="synthetic forwarder",
            deleted_at=datetime.now(UTC) if state == "deleted" else None,
        )
        session.add(company)
        session.flush()
        if state != "role_missing":
            session.add(
                CompanyRole(
                    organization_id=company.organization_id, company_id=company.id, role="FORWARDER"
                )
            )
        forwarder_id = uuid4() if state == "missing" else company.id
    body = {**body, "forwarder_company_id": str(forwarder_id)}
    before, before_counts = snapshot(f), counts(f)
    with f.session_factory() as session:
        companies = list(session.execute(select(Company.__table__).order_by(Company.id)).mappings())
    service = ShipmentCommandService(f.session_factory)
    response = f.client.post(
        "/api/v1/shipments",
        json=body,
        headers=f.headers("quotation-manager", f.organization_a) | {"Idempotency-Key": "forwarder"},
    )
    if state == "active":
        assert response.status_code == 201, response.text
        assert response.json()["forwarder_company_id"] == str(forwarder_id)
        after = snapshot(f)
        assert (
            str(service.create(context, body, idempotency_key="forwarder")[0].id)
            == response.json()["id"]
        )
        assert snapshot(f) == after
    else:
        expected_status = 409 if state == "role_missing" else 404
        expected_code = (
            "FORWARDER_ROLE_REQUIRED" if state == "role_missing" else "FORWARDER_NOT_FOUND"
        )
        assert response.status_code == expected_status, response.text
        assert response.json()["code"] == expected_code
        with pytest.raises(ApiProblem) as denied:
            service.create(context, body, idempotency_key="service-forwarder")
        assert (denied.value.status, denied.value.code) == (expected_status, expected_code)
        assert snapshot(f) == before
        assert counts(f) == before_counts
    with f.session_factory() as session:
        assert (
            list(session.execute(select(Company.__table__).order_by(Company.id)).mappings())
            == companies
        )
