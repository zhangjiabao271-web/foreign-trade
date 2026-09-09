from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.auth.errors import ApiProblem
from app.export.repositories import CustomsRepository, RefundRepository
from test_export_acceptance_matrix import prepare_case, snapshot
from test_sales_foreign_commands import foreign_manager

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")


@pytest.mark.parametrize("refund", [False, True])
def test_case_cursor_requires_live_tenant_owned_anchor(quotation_fixture, fake_storage, refund):
    f = quotation_fixture
    _, _, model, case_id = prepare_case(f, fake_storage, refund)
    foreign_manager(f)
    path = "tax-refund-cases" if refund else "customs-declarations"
    repository_type = RefundRepository if refund else CustomsRepository
    own_headers = f.headers("quotation-manager", f.organization_a)
    other_headers = f.headers("quotation-other", f.organization_b)
    before = snapshot(f, model, case_id)
    for organization_id, headers, cursor in (
        (f.organization_b, other_headers, case_id),
        (f.organization_a, own_headers, uuid4()),
    ):
        with f.session_factory() as session, pytest.raises(ApiProblem) as denied:
            repository_type(session).page(organization_id=organization_id, cursor=cursor, limit=1)
        assert denied.value.status == 404
        response = f.client.get(f"/api/v1/{path}", headers=headers, params={"cursor": str(cursor)})
        assert response.status_code == 404
        assert response.json()["code"] == "INVALID_CURSOR"
        assert snapshot(f, model, case_id) == before
    valid = f.client.get(f"/api/v1/{path}", headers=own_headers, params={"cursor": str(case_id)})
    assert valid.status_code == 200
    assert valid.json()["items"] == []
    with f.session_factory.begin() as session:
        session.get(model, case_id).deleted_at = datetime.now(UTC)
    before = snapshot(f, model, case_id)
    deleted = f.client.get(f"/api/v1/{path}", headers=own_headers, params={"cursor": str(case_id)})
    assert deleted.status_code == 404
    assert snapshot(f, model, case_id) == before
