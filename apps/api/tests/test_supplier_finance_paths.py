from dataclasses import replace
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.finance.supplier_models import Payable, SupplierPayment, SupplierPaymentAllocation
from app.finance.supplier_queries import SupplierFinanceQuery
from app.finance.supplier_repositories import SupplierFinanceRepository
from app.finance.supplier_services import SupplierFinanceService
from sqlalchemy import select
from test_customer_finance_tenant_paths import facts as customer_facts
from test_sales_foreign_commands import foreign_manager
from test_supplier_settlement import allocate_body, payable_body, payment_body, purchase, request

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def facts(f):
    with f.session_factory() as session:
        return customer_facts(f) | {
            model.__tablename__: [
                dict(row)
                for row in session.execute(select(model.__table__).order_by(model.id)).mappings()
            ]
            for model in (Payable, SupplierPayment, SupplierPaymentAllocation)
        }


def test_supplier_finance_all_tenant_paths(quotation_fixture):
    f = quotation_fixture
    po = purchase(f)
    payable = request(f, "/payables", body=payable_body(po))
    payment = request(f, "/supplier-payments", body=payment_body(po))
    allocated = request(
        f,
        f"/supplier-payments/{payment['id']}/allocate",
        body=allocate_body(payment, payable),
        status=200,
    )
    reversal = request(
        f,
        f"/supplier-payments/{payment['id']}/reverse",
        body={
            "expected_version": allocated["version"],
            "reason": "Synthetic scope reversal",
        },
    )
    foreign = foreign_manager(f)
    payable_id, payment_id = UUID(payable["id"]), UUID(payment["id"])
    filters = dict(supplier_id=None, currency=None, cursor=None, limit=20)
    before = facts(f)
    with f.session_factory() as session:
        repository = SupplierFinanceRepository(session)
        query = SupplierFinanceQuery(session)
        for lock in (False, True):
            assert repository.payable(f.organization_a, payable_id, lock=lock).id == payable_id
            assert repository.payment(f.organization_a, payment_id, lock=lock).id == payment_id
            with pytest.raises(ApiProblem) as denied:
                repository.payable(f.organization_b, payable_id, lock=lock)
            assert denied.value.status == 404
            with pytest.raises(ApiProblem) as denied:
                repository.payment(f.organization_b, payment_id, lock=lock)
            assert denied.value.status == 404
        assert len(repository.payables(f.organization_a, purchase_id=None, **filters)) == 1
        assert len(repository.payments(f.organization_a, **filters)) == 2
        assert repository.payables(f.organization_b, purchase_id=None, **filters) == []
        assert repository.payments(f.organization_b, **filters) == []
        assert len(repository.allocations(f.organization_a, {payment_id})) == 1
        assert repository.allocations(f.organization_b, {payment_id}) == []
        assert repository.paid_totals(f.organization_a, {payable_id}) == {payable_id: 0}
        assert repository.paid_totals(f.organization_b, {payable_id}) == {}
        assert repository.reversals(f.organization_a, {payment_id}) == {
            payment_id: UUID(reversal["id"])
        }
        assert repository.reversals(f.organization_b, {payment_id}) == {}
        for ids in (set(), {UUID(reversal["id"])}):
            assert repository.reversals(f.organization_b, ids) == {}
        for context, status in ((foreign, 404), (replace(foreign, permissions=frozenset()), 403)):
            with pytest.raises(ApiProblem) as denied:
                query.payable(context, payable_id)
            assert denied.value.status == status
            with pytest.raises(ApiProblem) as denied:
                query.payment(context, payment_id)
            assert denied.value.status == status
        assert query.payables(foreign, purchase_id=None, **filters).items == []
        assert query.payments(foreign, **filters).items == []

    version_request = {"expected_version": 1, "reason": "Synthetic foreign command"}
    allocation_request = allocate_body(payment, payable)
    service = SupplierFinanceService(f.session_factory)
    operations = (
        (
            "/payables",
            payable_body(po),
            lambda: service.create_payable(foreign, payable_body(po), key="foreign"),
        ),
        (
            f"/payables/{payable_id}/void",
            version_request,
            lambda: service.void_payable(foreign, payable_id, version_request, key="foreign"),
        ),
        (
            "/supplier-payments",
            payment_body(po),
            lambda: service.record_payment(foreign, payment_body(po), key="foreign"),
        ),
        (
            f"/supplier-payments/{payment_id}/allocate",
            allocation_request,
            lambda: service.allocate(foreign, payment_id, allocation_request, key="foreign"),
        ),
        (
            f"/supplier-payments/{payment_id}/reverse",
            version_request,
            lambda: service.reverse(foreign, payment_id, version_request, key="foreign"),
        ),
    )
    headers = {**f.headers("quotation-other", f.organization_b), "Idempotency-Key": "foreign"}
    for path, body, operation in operations:
        response = f.client.post(f"/api/v1{path}", headers=headers, json=body)
        assert response.status_code == 404, response.text
        with pytest.raises(ApiProblem) as denied:
            operation()
        assert denied.value.status == 404
        assert facts(f) == before
    for path in (
        f"/payables/{payable_id}",
        f"/supplier-payments/{payment_id}",
        f"/payables?cursor={payable_id}",
        f"/supplier-payments?cursor={payment_id}",
    ):
        assert f.client.get(f"/api/v1{path}", headers=headers).status_code == 404
    for path in ("/payables", "/supplier-payments"):
        response = f.client.get(f"/api/v1{path}", headers=headers)
        assert response.status_code == 200
        assert response.json()["items"] == []
    assert facts(f) == before
