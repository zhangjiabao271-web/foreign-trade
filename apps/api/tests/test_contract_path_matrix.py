from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import permissions_for_role
from app.documents.models import Document, DocumentLink, DocumentVersion
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.sales.contract_models import SalesContract
from app.sales.contract_services import ContractQuery, ContractRepository, ContractService
from app.sales.models import SalesOrder, SalesOrderItem
from app.work.models import Activity
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_order_procurement_vertical_slice import create_confirmed_order
from test_sales_contracts import create, evidence, request, sign

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(session.execute(select(model.__table__).order_by(model.id)))
            for model in (
                SalesOrder,
                SalesOrderItem,
                SalesContract,
                Document,
                DocumentVersion,
                DocumentLink,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        }


def command(order, contract, document_version, action):
    path = f"/api/v1/sales-orders/{order['id']}/contracts"
    if action == "created":
        return "POST", path, {"external_reference": "ROLE-MATRIX"}
    path += f"/{contract['id']}"
    body = {"expected_version": contract["version"], "reason": "Synthetic contract review"}
    if action == "updated":
        return "PUT", path, body | {"external_reference": "UPDATED-MATRIX"}
    if action == "signed":
        return (
            "POST",
            path + "/record-signature",
            body
            | {
                "signed_on": "2026-01-01",
                "document_version_id": str(document_version),
            },
        )
    return "POST", path + "/void", body


@pytest.mark.parametrize("role", list(MembershipRole))
@pytest.mark.parametrize("action", ["created", "updated", "signed", "voided"])
def test_contract_commands_six_roles_and_service_replay(quotation_fixture, role, action):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    contract = None if action == "created" else create(f, order)
    _, document_version = evidence(f, order)
    method, path, body = command(order, contract, document_version, action)
    with f.session_factory.begin() as session:
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_a,
                OrganizationMembership.user_id == f.sales_user,
            )
        )
        member.role = role
    context = RequestContext(f.sales_user, f.organization_a, permissions_for_role(role), uuid4())
    headers = f.headers("quotation-sales", f.organization_a) | {"Idempotency-Key": "role-matrix"}

    def invoke():
        return ContractService(f.session_factory).execute(
            context,
            UUID(order["id"]),
            action=action,
            data=body,
            key="role-matrix",
            contract_id=UUID(contract["id"]) if contract else None,
        )

    before = snapshot(f)
    parent = f"/api/v1/sales-orders/{order['id']}/contracts"
    listed = f.client.get(parent, headers=headers)
    assert listed.status_code == 200
    if contract:
        read = f.client.get(parent + f"/{contract['id']}", headers=headers)
        assert read.status_code == 200
        assert read.json()["id"] == contract["id"]
        assert [item["id"] for item in listed.json()["items"]] == [contract["id"]]
    else:
        assert listed.json()["items"] == []
    assert snapshot(f) == before
    response = f.client.request(method, path, headers=headers, json=body)
    allowed = role in {MembershipRole.ADMIN, MembershipRole.MANAGER} or (
        role == MembershipRole.SALES and action != "signed"
    )
    if not allowed:
        assert response.status_code == 403
        assert response.json()["code"] == "PERMISSION_DENIED"
        with pytest.raises(ApiProblem) as denied:
            invoke()
        assert denied.value.code == "PERMISSION_DENIED"
        assert snapshot(f) == before
        return
    assert response.status_code == (201 if action == "created" else 200), response.text
    result = response.json()
    assert (
        result["status"]
        == {"created": "DRAFT", "updated": "DRAFT", "signed": "SIGNED", "voided": "VOIDED"}[action]
    )
    after = snapshot(f)
    for table in ("activities", "audit_logs", "outbox_events", "idempotency_keys"):
        assert len(after[table]) == len(before[table]) + 1
    assert f.client.request(method, path, headers=headers, json=body).json() == result
    assert invoke().id == UUID(result["id"])
    assert snapshot(f) == after


@pytest.mark.parametrize("state", ["SIGNED", "VOIDED"])
@pytest.mark.parametrize("action", ["updated", "signed", "voided"])
def test_all_final_contract_commands_reject_without_writes(quotation_fixture, state, action):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    contract = create(f, order)
    _, version = evidence(f, order)
    if state == "SIGNED":
        contract = sign(f, order, contract, version)
    else:
        contract = request(
            f,
            order,
            suffix=f"/{contract['id']}/void",
            body={
                "expected_version": contract["version"],
                "reason": "Synthetic void",
            },
        )
    method, path, body = command(order, contract, version, action)
    before = snapshot(f)
    response = f.client.request(
        method,
        path,
        json=body,
        headers={
            **f.headers("quotation-manager", f.organization_a),
            "Idempotency-Key": "final-command",
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CONTRACT_IMMUTABLE"
    assert snapshot(f) == before


def test_contract_foreign_http_repository_and_query_paths(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    contract = create(f, order)
    _, version = evidence(f, order)
    order_id, contract_id = UUID(order["id"]), UUID(contract["id"])
    with f.session_factory.begin() as session:
        session.add(
            OrganizationMembership(
                organization_id=f.organization_b,
                user_id=f.sales_user,
                role="MANAGER",
                status="ACTIVE",
            )
        )
    headers = f.headers("quotation-sales", f.organization_b) | {
        "Idempotency-Key": "foreign-command"
    }
    assert f.client.get("/api/v1/me/context", headers=headers).status_code == 200
    before = snapshot(f)
    parent = f"/api/v1/sales-orders/{order_id}/contracts"
    review_path = f"/api/v1/commercial-text/sales_contract/{contract_id}/review"
    own_review = f.client.get(review_path, headers=f.headers("quotation-manager", f.organization_a))
    assert own_review.status_code == 200
    review_body = {
        "expected_version": own_review.json()["version"],
        "content_digest": own_review.json()["content_digest"],
        "release": True,
        "confirmed": True,
        "reason": "Synthetic foreign contract review",
    }
    for method in ("GET", "POST"):
        response = f.client.request(
            method,
            review_path,
            headers=headers,
            **({"json": review_body} if method == "POST" else {}),
        )
        assert response.status_code == 404
        assert snapshot(f) == before
    for path in (parent, parent + f"/{contract_id}", parent + f"?cursor={contract_id}"):
        response = f.client.get(path, headers=headers)
        assert response.status_code == 404
        assert snapshot(f) == before
    foreign = RequestContext(
        f.sales_user, f.organization_b, permissions_for_role(MembershipRole.MANAGER), uuid4()
    )
    for action in ("created", "updated", "signed", "voided"):
        method, path, body = command(order, contract, version, action)
        response = f.client.request(method, path, json=body, headers=headers)
        assert response.status_code == 404
        with pytest.raises(ApiProblem) as missing:
            ContractService(f.session_factory).execute(
                foreign,
                order_id,
                action=action,
                data=body,
                key="foreign-service",
                contract_id=contract_id if action != "created" else None,
            )
        assert missing.value.status == 404
        assert snapshot(f) == before
    with f.session_factory() as session:
        repository, query = ContractRepository(session), ContractQuery(session)
        assert not repository.list(f.organization_b, order_id, cursor=None, limit=20)
        for read in (
            lambda: repository.order(f.organization_b, order_id, lock=True),
            lambda: repository.get(f.organization_b, order_id, contract_id, lock=True),
            lambda: repository.list(f.organization_b, order_id, cursor=contract_id, limit=20),
            lambda: query.list(foreign, order_id, cursor=None, limit=20),
            lambda: query.get(foreign, order_id, contract_id),
        ):
            with pytest.raises(ApiProblem) as missing:
                read()
            assert missing.value.status == 404
    with Session() as session:
        query = ContractQuery(session)
        denied = replace(foreign, permissions=frozenset())
        for read in (
            lambda: query.list(denied, order_id, cursor=None, limit=20),
            lambda: query.get(denied, order_id, contract_id),
        ):
            with pytest.raises(ApiProblem) as missing:
                read()
            assert missing.value.status == 403
            assert not session.in_transaction()
    assert snapshot(f) == before
