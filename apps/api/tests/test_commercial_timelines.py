from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.fulfillment.models import Shipment
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.sales.models import Quotation, SalesOrder
from app.work.models import Activity
from app.work.services import WorkQueryService
from sqlalchemy import event, select
from test_quotation_vertical_slice import table_counts
from test_shipment_documents_vertical_slice import create_shipment, executing_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


@pytest.mark.parametrize(
    "kind,model,resource,suffix,permission",
    [
        ("quotation", Quotation, "quotations", "activities", Permission.QUOTATION_READ),
        ("shipment", Shipment, "shipments", "activities", Permission.SHIPMENT_READ),
        ("sales_order", SalesOrder, "sales-orders", "activity-history", Permission.ORDER_READ),
    ],
)
def test_commercial_history_is_complete_protected_and_owner_scoped(
    quotation_fixture, kind, model, resource, suffix, permission
):
    f = quotation_fixture
    order = executing_order(f)
    create_shipment(
        f,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    )
    with f.session_factory() as session:
        owner = session.scalars(
            select(model).where(model.organization_id == f.organization_a)
        ).one()
        owner_id = owner.id
    seeded_ids = [uuid4() for _ in range(105)]
    alien_cursor = uuid4()
    with f.session_factory.begin() as session:
        for identifier in seeded_ids:
            session.add(
                Activity(
                    id=identifier,
                    organization_id=f.organization_a,
                    subject_type=kind,
                    subject_id=owner_id,
                    activity_type="acceptance.history",
                    summary="Confidential history text",
                    details={"internal_cost": "999.1234"},
                    correlation_id=uuid4(),
                    occurred_at=datetime(2099, 1, 1, tzinfo=UTC),
                )
            )
        session.add(
            Activity(
                id=alien_cursor,
                organization_id=f.organization_a,
                subject_type=kind,
                subject_id=uuid4(),
                activity_type="acceptance.other",
                summary="Other owner",
                details={},
                correlation_id=uuid4(),
            )
        )
    before = table_counts(f)
    path = f"/api/v1/{resource}/{owner_id}/{suffix}"
    manager = f.headers("quotation-manager", f.organization_a)
    cursor = None
    seen = []
    for _ in range(10):
        params = {"limit": 20}
        if cursor:
            params["cursor"] = cursor
        response = f.client.get(path, headers=manager, params=params)
        assert response.status_code == 200, response.text
        body = response.json()
        seen.extend(item["id"] for item in body["items"])
        if not body["has_more"]:
            assert body["next_cursor"] is None
            break
        assert len(body["items"]) == 20
        cursor = body["next_cursor"]
    else:
        pytest.fail("History did not terminate")
    assert len(seen) == len(set(seen))
    assert seen[:105] == [str(value) for value in sorted(seeded_ids, reverse=True)]
    assert str(alien_cursor) not in seen
    assert len(seen) > 105  # Original business activity is also reachable.
    low = f.client.get(path, headers=f.headers("quotation-sales", f.organization_a))
    assert low.status_code == 200, low.text
    assert "Confidential history text" not in low.text and "999.1234" not in low.text
    assert all(row["summary"] is None and row["details"] == {} for row in low.json()["items"])
    for role in MembershipRole:
        with f.session_factory.begin() as session:
            membership = session.scalars(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == f.organization_a,
                    OrganizationMembership.user_id == f.sales_user,
                )
            ).one()
            membership.role = role
        role_response = f.client.get(path, headers=f.headers("quotation-sales", f.organization_a))
        assert role_response.status_code == 200, (role, role_response.text)
        can_read_cost = role in {
            MembershipRole.ADMIN,
            MembershipRole.MANAGER,
            MembershipRole.FINANCE,
        }
        assert ("999.1234" in role_response.text) is can_read_cost
    with f.session_factory.begin() as session:
        membership = session.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_a,
                OrganizationMembership.user_id == f.sales_user,
            )
        ).one()
        membership.role = MembershipRole.SALES
    foreign = f.client.get(path, headers=f.headers("quotation-other", f.organization_b))
    assert foreign.status_code == 404, foreign.text
    bad_cursor = f.client.get(path, headers=manager, params={"cursor": str(alien_cursor)})
    assert bad_cursor.status_code == 400
    assert bad_cursor.json()["code"] == "INVALID_CURSOR"
    assert f.client.get(path, headers=manager, params={"limit": 101}).status_code == 422
    assert f.client.get(path).status_code == 401
    assert table_counts(f) == before

    safe_id = uuid4()
    with f.session_factory.begin() as session:
        session.add(
            Activity(
                id=safe_id,
                organization_id=f.organization_a,
                subject_type=kind,
                subject_id=owner_id,
                activity_type="acceptance.safe_note",
                summary="Reviewed delivery reminder",
                details={"note": "Check document readiness"},
                correlation_id=uuid4(),
                occurred_at=datetime(2100, 1, 1, tzinfo=UTC),
            )
        )
    review_path = (
        f"/api/v1/sales-orders/{owner_id}/work/activity/{safe_id}/review"
        if kind == "sales_order"
        else f"/api/v1/work/{kind}/{owner_id}/activities/{safe_id}/review"
    )
    snapshot = f.client.get(review_path, headers=manager)
    assert snapshot.status_code == 200, snapshot.text
    body = snapshot.json()
    decision = {
        "expected_version": body["version"],
        "content_digest": body["content_digest"],
        "release": True,
        "reason": "Checked no internal pricing",
        "confirmed": True,
    }
    sales_headers = f.headers("quotation-sales", f.organization_a)
    assert f.client.get(review_path, headers=sales_headers).status_code == 403
    approved = f.client.post(
        review_path,
        headers=manager | {"Idempotency-Key": str(uuid4())},
        json=decision,
    )
    assert approved.status_code == 200, approved.text
    visible = f.client.get(path, headers=sales_headers).json()["items"]
    released = next(row for row in visible if row["id"] == str(safe_id))
    assert released["summary"] == "Reviewed delivery reminder" and released["released"] is True
    assert "999.1234" not in str(visible)
    with f.session_factory.begin() as session:
        session.get(Activity, safe_id).summary = "Changed confidential reminder"
    changed = f.client.get(path, headers=sales_headers).json()["items"]
    assert next(row for row in changed if row["id"] == str(safe_id))["summary"] is None

    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    with f.session_factory() as session:
        service = WorkQueryService(session)
        statements = []

        def counted(*args):
            statements.append(args[2])

        event.listen(f.engine, "before_cursor_execute", counted)
        try:
            first = service.commercial_activities(context, kind, owner_id, cursor=None, limit=20)
            assert len(statements) == 2
            statements.clear()
            service.commercial_activities(
                context, kind, owner_id, cursor=first.next_cursor, limit=20
            )
            assert len(statements) == 3
            statements.clear()
            with pytest.raises(ApiProblem) as denied:
                service.commercial_activities(
                    replace(context, permissions=context.permissions - {permission}),
                    kind,
                    owner_id,
                    cursor=None,
                    limit=20,
                )
            assert denied.value.status == 403
            assert statements == []
        finally:
            event.remove(f.engine, "before_cursor_execute", counted)
    with f.session_factory.begin() as session:
        session.get(model, owner_id).deleted_at = datetime.now(UTC)
    assert f.client.get(path, headers=manager).status_code == 404
