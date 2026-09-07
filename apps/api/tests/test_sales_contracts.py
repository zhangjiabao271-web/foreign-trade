from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.models import Company
from app.documents.models import Document, DocumentLink, DocumentVersion
from app.platform.models import AuditLog, OutboxEvent
from app.sales.contract_models import SalesContract
from app.sales.contract_services import ContractQuery, ContractService
from app.sales.models import SalesOrder
from app.work.models import Activity
from legacy_migration import verify_legacy_guard
from sqlalchemy import event, func, select
from test_order_procurement_vertical_slice import create_confirmed_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def request(
    f, order, method="post", suffix="", body=None, key=None, subject="quotation-manager", status=200
):
    response = getattr(f.client, method)(
        f"/api/v1/sales-orders/{order['id']}/contracts{suffix}",
        **({"json": body or {}} if method != "get" else {}),
        headers={**f.headers(subject, f.organization_a), "Idempotency-Key": key or str(uuid4())},
    )
    assert response.status_code == status, response.text
    return response.json()


def create(f, order, key=None):
    return request(
        f,
        order,
        body={"external_reference": "CLIENT-2026", "notes": "Confirmed commercial terms"},
        key=key,
        status=201,
    )


def evidence(
    f,
    order,
    *,
    organization_id=None,
    status="AVAILABLE",
    kind="SALES_CONTRACT",
    pinned="immutable-storage-version",
):
    org = organization_id or f.organization_a
    with f.session_factory.begin() as session:
        doc = Document(organization_id=org, title="Signed contract", document_type=kind)
        session.add(doc)
        session.flush()
        version = DocumentVersion(
            organization_id=org,
            document_id=doc.id,
            version_number=1,
            status=status,
            object_key=f"{org}/{uuid4()}",
            storage_version_id=pinned,
            file_name="signed.pdf",
            mime_type="application/pdf",
            expected_size_bytes=10,
            expected_sha256="a" * 64,
            actual_sha256="a" * 64,
            actual_size_bytes=10,
        )
        session.add_all(
            [
                version,
                DocumentLink(
                    organization_id=org,
                    document_id=doc.id,
                    target_type="SALES_ORDER",
                    target_id=UUID(order["id"]),
                ),
            ]
        )
        session.flush()
        return doc.id, version.id


def sign(f, order, contract, version, *, status=200, subject="quotation-manager", key=None):
    return request(
        f,
        order,
        suffix=f"/{contract['id']}/record-signature",
        body={
            "expected_version": contract["version"],
            "reason": "Reviewed signed counterpart",
            "signed_on": "2026-01-01",
            "document_version_id": str(version),
        },
        status=status,
        subject=subject,
        key=key,
    )


def counts(f):
    with f.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (SalesContract, Activity, AuditLog, OutboxEvent)
        )


def test_contract_snapshot_signature_immutability_and_idempotency(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    contract = create(f, order, key="create-once")
    baseline = counts(f)
    assert create(f, order, key="create-once") == contract
    assert counts(f) == baseline
    assert contract["total"] == order["total"]
    snapshot = contract["commercial_snapshot"]
    assert snapshot["items"][0]["quantity"] == order["items"][0]["quantity"]
    assert "cost" not in str(snapshot) and "profit" not in str(snapshot)
    with f.session_factory.begin() as session:
        session.get(Company, UUID(order["company_id"])).name = "Changed after draft"
    updated = request(
        f,
        order,
        "put",
        f"/{contract['id']}",
        {
            "expected_version": contract["version"],
            "reason": "Correct external reference",
            "external_reference": "CLIENT-NEW",
            "notes": "Document reviewed",
        },
    )
    assert updated["commercial_snapshot"] == snapshot
    assert updated["version"] > contract["version"]
    doc, version = evidence(f, order)
    signed = sign(f, order, updated, version, key="sign-once")
    baseline = counts(f)
    assert sign(f, order, updated, version, key="sign-once") == signed
    assert counts(f) == baseline
    assert signed["status"] == "SIGNED" and signed["signed_document_version_id"] == str(version)
    for suffix, method in [("/void", "post"), ("", "put")]:
        assert (
            request(
                f,
                order,
                method,
                f"/{signed['id']}{suffix}",
                {"expected_version": signed["version"], "reason": "Cannot overwrite signed facts"},
                status=409,
            )["code"]
            == "CONTRACT_IMMUTABLE"
        )
    with f.session_factory.begin() as session:
        session.get(Document, doc).latest_version_number = 2
        session.add(
            DocumentVersion(
                organization_id=f.organization_a,
                document_id=doc,
                version_number=2,
                status="AVAILABLE",
                object_key=f"{f.organization_a}/{uuid4()}",
                storage_version_id="new-storage-version",
                file_name="replacement.pdf",
                mime_type="application/pdf",
                expected_size_bytes=20,
                actual_size_bytes=20,
                expected_sha256="b" * 64,
                actual_sha256="b" * 64,
            )
        )
    assert request(f, order, "get", f"/{signed['id']}")["signed_document_version_id"] == str(
        version
    )
    assert request(f, order, "get", f"/{signed['id']}")["commercial_snapshot"] == snapshot
    with f.session_factory() as session:
        audits = session.scalars(
            select(AuditLog).where(AuditLog.target_id == UUID(signed["id"]))
        ).all()
        assert len(audits) == 3 and all(a.actor_user_id is not None for a in audits)
        events = session.scalars(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == UUID(signed["id"]))
        ).all()
        assert all(set(e.payload) == {"contract_id", "sales_order_id"} for e in events)


@pytest.mark.parametrize(
    "status,kind,pinned,expected",
    [
        ("SCANNING", "SALES_CONTRACT", "fixed", 409),
        ("AVAILABLE", "OTHER", "fixed", 404),
        ("AVAILABLE", "SALES_CONTRACT", None, 409),
        ("AVAILABLE", "SALES_CONTRACT", "null", 409),
    ],
)
def test_contract_rejects_unready_or_wrong_evidence(
    quotation_fixture, status, kind, pinned, expected
):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    contract = create(f, order)
    _, version = evidence(f, order, status=status, kind=kind, pinned=pinned)
    before = counts(f)
    sign(f, order, contract, version, status=expected)
    assert counts(f) == before


def test_contract_tenant_parent_permissions_and_version_guards(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    contract = create(f, order)
    _, version = evidence(f, order, organization_id=f.organization_b)
    sign(f, order, contract, version, status=404)
    sign(f, order, contract, version, status=403, subject="quotation-sales")
    request(f, order, body={}, subject="quotation-finance", status=403)
    response = f.client.get(
        f"/api/v1/sales-orders/{order['id']}/contracts",
        headers=f.headers("quotation-other", f.organization_b),
    )
    assert response.status_code == 404
    fake = {"id": str(uuid4())}
    request(f, fake, "get", f"/{contract['id']}", status=404)
    request(
        f,
        order,
        "put",
        f"/{contract['id']}",
        {"expected_version": 999, "reason": "Stale edit"},
        status=409,
    )
    request(f, order, body={"total": "0"}, status=422)
    with f.session_factory() as session:
        context = RequestContext(
            user_id=f.sales_user,
            organization_id=f.organization_a,
            permissions=frozenset(),
            request_id=uuid4(),
        )
        with pytest.raises(ApiProblem) as error:
            ContractQuery(session).get(context, UUID(order["id"]), UUID(contract["id"]))
        assert error.value.status == 403


def test_void_preserves_history_allows_new_draft_and_pages(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    first = create(f, order)
    request(f, order, status=409)
    void = request(
        f,
        order,
        suffix=f"/{first['id']}/void",
        body={"expected_version": first["version"], "reason": "Duplicate draft preparation"},
    )
    assert void["status"] == "VOIDED"
    second = create(f, order)
    page = f.client.get(
        f"/api/v1/sales-orders/{order['id']}/contracts?limit=1",
        headers=f.headers("quotation-sales", f.organization_a),
    ).json()
    assert page["items"][0]["id"] == second["id"] and page["has_more"]
    page2 = f.client.get(
        f"/api/v1/sales-orders/{order['id']}/contracts?limit=1&cursor={page['next_cursor']}",
        headers=f.headers("quotation-sales", f.organization_a),
    ).json()
    assert page2["items"][0]["id"] == first["id"] and not page2["has_more"]


@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_contract_command_rolls_back_all_evidence(quotation_fixture, table):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    before = counts(f)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith(f"INSERT INTO {table}"):
            raise RuntimeError("Injected evidence failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="Injected evidence failure"):
            create(f, order)
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before


def test_concurrent_contract_creation_serializes_and_downgrade_preserves_data(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.CONTRACT_WRITE}),
        request_id=uuid4(),
    )

    def run(_):
        try:
            return (
                ContractService(f.session_factory)
                .execute(context, UUID(order["id"]), action="created", data={}, key=str(uuid4()))
                .id
            )
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sum(isinstance(r, UUID) for r in results) == 1
    assert "CONTRACT_ALREADY_EXISTS" in results
    verify_legacy_guard(f.engine, "20260906_0018", "20260906_0017", "Contract evidence exists")
    assert counts(f)[0] == 1


@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_signature_failure_preserves_draft_and_evidence(quotation_fixture, table):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    contract = create(f, order)
    _, version = evidence(f, order)
    before = counts(f)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith(f"INSERT INTO {table}"):
            raise RuntimeError("Injected signature evidence failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="Injected signature evidence failure"):
            sign(f, order, contract, version)
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    current = request(f, order, "get", f"/{contract['id']}")
    assert current == contract


@pytest.mark.parametrize("state", ["CANCELLED", "COMPLETED"])
def test_finalized_orders_reject_new_contracts_and_draft_changes(quotation_fixture, state):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    contract = create(f, order)
    with f.session_factory.begin() as session:
        session.get(SalesOrder, UUID(order["id"])).status = state
    before = counts(f)
    assert request(f, order, status=409)["code"] == "CONTRACT_ORDER_FINALIZED"
    request(
        f,
        order,
        "put",
        f"/{contract['id']}",
        {"expected_version": contract["version"], "reason": "Attempt after finalization"},
        status=409,
    )
    assert counts(f) == before
    assert request(f, order, "get", f"/{contract['id']}")["status"] == "DRAFT"


def test_signature_needs_confirmed_order_past_date_and_same_order_evidence(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    contract = create(f, order)
    doc, version = evidence(f, order)
    with f.session_factory.begin() as session:
        session.get(SalesOrder, UUID(order["id"])).status = "DRAFT"
    assert sign(f, order, contract, version, status=409)["code"] == "ORDER_NOT_CONFIRMED"
    with f.session_factory.begin() as session:
        session.get(SalesOrder, UUID(order["id"])).status = "EXECUTING"
    request(
        f,
        order,
        suffix=f"/{contract['id']}/record-signature",
        body={
            "expected_version": contract["version"],
            "reason": "Reject future signature",
            "signed_on": "2099-01-01",
            "document_version_id": str(version),
        },
        status=422,
    )
    with f.session_factory.begin() as session:
        link = session.scalar(select(DocumentLink).where(DocumentLink.document_id == doc))
        link.target_id = uuid4()
    assert sign(f, order, contract, version, status=404)["code"] == "CONTRACT_EVIDENCE_NOT_FOUND"
