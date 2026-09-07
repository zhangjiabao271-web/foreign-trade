from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.crm.models import Opportunity
from app.crm.opportunity_services import OpportunityCommandService
from app.platform.records import AuditRecorder, OutboxRecorder
from app.sales.services import QuotationCommandService
from app.work.models import Activity
from legacy_migration import verify_legacy_guard, verify_legacy_upgrade
from sqlalchemy.orm import Session
from test_migrations import alembic_config
from test_quotation_vertical_slice import (
    create_commercial_inputs,
    create_opportunity,
    post_ok,
    post_state,
    state_request,
    table_counts,
)

pytest_plugins = ("test_quotation_vertical_slice",)


def headers(f, key="opportunity-command", subject="quotation-sales"):
    return f.headers(subject, f.organization_a) | {"Idempotency-Key": key}


def prepare_sent(f):
    data, _, opportunity_id = create_commercial_inputs(f)
    quote = post_ok(f, "/api/v1/quotations", "quotation-manager", data, 201)
    path = f"/api/v1/quotations/{quote['id']}"
    post_ok(f, path + "/submit", "quotation-sales")
    post_ok(f, path + "/approve", "quotation-manager")
    post_ok(f, path + "/send", "quotation-sales")
    return quote["id"], opportunity_id


def test_loss_reason_permission_tenant_and_replay(quotation_fixture):
    f = quotation_fixture
    _, record_id = create_opportunity(f)
    path = f"/api/v1/opportunities/{record_id}"
    row = f.client.get(path, headers=headers(f)).json()
    data = {"expected_version": row["version"], "reason": "Customer cancelled project"}
    assert (
        f.client.post(
            path + "/mark-lost", headers=headers(f, subject="quotation-operations"), json=data
        ).status_code
        == 403
    )
    foreign = f.headers("quotation-other", f.organization_b) | {"Idempotency-Key": "foreign"}
    for suffix in ("", "/activities"):
        assert f.client.get(path + suffix, headers=foreign).status_code == 404
    assert f.client.post(path + "/mark-lost", headers=foreign, json=data).status_code == 404
    assert f.client.get("/api/v1/opportunities", headers=foreign).json()["items"] == []
    assert (
        f.client.post(
            path + "/mark-lost", headers=headers(f), json={**data, "reason": "  "}
        ).status_code
        == 422
    )
    before = table_counts(f)
    response = f.client.post(path + "/mark-lost", headers=headers(f), json=data)
    assert response.status_code == 200, response.text
    lost = response.json()
    assert lost["status"] == "LOST" and lost["lost_at"]
    assert lost["lost_reason"] is None
    assert (
        f.client.get(path, headers=f.headers("quotation-manager", f.organization_a)).json()[
            "lost_reason"
        ]
        == data["reason"]
    )
    assert f.client.post(path + "/mark-lost", headers=headers(f), json=data).json() == lost
    assert tuple(after - old for old, after in zip(before, table_counts(f), strict=True)) == (
        1,
        1,
        1,
    )
    assert (
        f.client.post(
            path + "/mark-lost",
            headers=headers(f, "new-key"),
            json={**data, "expected_version": lost["version"]},
        ).status_code
        == 409
    )


def test_negotiation_and_acceptance_win_with_separate_history(quotation_fixture):
    f = quotation_fixture
    quote_id, record_id = prepare_sent(f)
    path = f"/api/v1/opportunities/{record_id}"
    row = f.client.get(path, headers=headers(f)).json()
    response = f.client.post(
        path + "/start-negotiation",
        headers=headers(f),
        json={"expected_version": row["version"], "reason": "Discuss delivery evidence"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "NEGOTIATION"
    post_ok(f, f"/api/v1/quotations/{quote_id}/accept", "quotation-sales")
    won = f.client.get(path, headers=headers(f)).json()
    assert won["status"] == "WON"
    assert (
        f.client.post(
            path + "/mark-lost",
            headers=headers(f, "loss"),
            json={"expected_version": won["version"], "reason": "Cannot undo won"},
        ).status_code
        == 409
    )
    history = f.client.get(path + "/activities?limit=1", headers=headers(f)).json()
    assert history["has_more"] and history["items"][0]["summary"] is None
    privileged = f.client.get(
        path + "/activities?limit=1", headers=f.headers("quotation-manager", f.organization_a)
    ).json()
    assert privileged["has_more"] and "赢单" in privileged["items"][0]["summary"]


def test_lost_opportunity_cannot_be_overwritten_by_acceptance(quotation_fixture):
    f = quotation_fixture
    quote_id, record_id = prepare_sent(f)
    path = f"/api/v1/opportunities/{record_id}"
    row = f.client.get(path, headers=headers(f)).json()
    assert (
        f.client.post(
            path + "/mark-lost",
            headers=headers(f),
            json={"expected_version": row["version"], "reason": "No budget"},
        ).status_code
        == 200
    )
    before = table_counts(f)
    assert post_state(f, f"/api/v1/quotations/{quote_id}/accept").status_code == 409
    assert table_counts(f) == before
    quote = f.client.get(f"/api/v1/quotations/{quote_id}", headers=headers(f)).json()
    assert quote["accepted_version_id"] is None
    assert quote["current_version"]["status"] == "SENT"


@pytest.mark.parametrize("recorder", [Activity, AuditRecorder, OutboxRecorder])
def test_loss_failure_rolls_back_all_records(quotation_fixture, monkeypatch, recorder):
    f = quotation_fixture
    _, record_id = create_opportunity(f)
    before = table_counts(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("injected opportunity failure")

    if recorder is Activity:
        original = Session.add

        def add(session, instance, *args, **kwargs):
            if isinstance(instance, Activity):
                fail()
            return original(session, instance, *args, **kwargs)

        monkeypatch.setattr(Session, "add", add)
    else:
        monkeypatch.setattr(recorder, "record", fail)
    with pytest.raises(RuntimeError, match="injected opportunity failure"):
        OpportunityCommandService(f.session_factory).execute(
            context,
            UUID(record_id),
            "mark-lost",
            {"expected_version": 1, "reason": "Failure test"},
            idempotency_key="failure",
        )
    assert table_counts(f) == before
    with f.session_factory() as session:
        row = session.get(Opportunity, UUID(record_id))
        assert row.status == "OPEN" and row.lost_reason is None and row.version == 1


def test_concurrent_loss_and_acceptance_have_one_winner(quotation_fixture):
    f = quotation_fixture
    quote_id, record_id = prepare_sent(f)
    row = f.client.get(f"/api/v1/opportunities/{record_id}", headers=headers(f)).json()
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )

    quotation_request = state_request(f, quote_id)

    def run(kind):
        try:
            if kind == "loss":
                OpportunityCommandService(f.session_factory).execute(
                    context,
                    UUID(record_id),
                    "mark-lost",
                    {"expected_version": row["version"], "reason": "No budget"},
                    idempotency_key="race",
                )
            else:
                QuotationCommandService(f.session_factory).accept(
                    context, UUID(quote_id), quotation_request, key="accept-race"
                )
            return "ok"
        except ApiProblem:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, ["loss", "accept"])) == ["conflict", "ok"]


def test_previous_opportunity_migration_preserves_source_and_guards_evidence(quotation_fixture):
    f = quotation_fixture
    _, record_id = create_opportunity(f)
    path = f"/api/v1/opportunities/{record_id}"
    before = f.client.get(path, headers=headers(f)).json()
    config = alembic_config(f.engine.url.render_as_string(hide_password=False))
    verify_legacy_upgrade(f.engine, "20260906_0013")
    command.check(config)
    assert f.client.get(path, headers=headers(f)).json() == before
    response = f.client.post(
        path + "/mark-lost",
        headers=headers(f),
        json={"expected_version": before["version"], "reason": "Archive evidence"},
    )
    assert response.status_code == 200
    verify_legacy_guard(f.engine, "20260906_0014", "20260906_0013", "loss evidence exists")
    assert f.client.get(path, headers=headers(f)).json() == response.json()


def test_opportunity_cursor_pages_and_foreign_cursor_are_scoped(quotation_fixture):
    f = quotation_fixture
    _, first_id = create_opportunity(f)
    with f.session_factory.begin() as session:
        first = session.get(Opportunity, UUID(first_id))
        # Independent source lead is required by the organization-level uniqueness rule.
        from app.crm.models import Lead

        lead = Lead(organization_id=f.organization_a, company_name="Second lead")
        session.add(lead)
        session.flush()
        session.add(
            Opportunity(
                organization_id=f.organization_a,
                company_id=first.company_id,
                source_lead_id=lead.id,
                name="Second opportunity",
            )
        )
    response = f.client.get("/api/v1/opportunities?limit=1", headers=headers(f)).json()
    assert len(response["items"]) == 1 and response["has_more"]
    second = f.client.get(
        f"/api/v1/opportunities?limit=1&cursor={response['next_cursor']}", headers=headers(f)
    ).json()
    assert len(second["items"]) == 1 and not second["has_more"]
    assert second["items"][0]["id"] != response["items"][0]["id"]
    foreign = f.headers("quotation-other", f.organization_b)
    assert (
        f.client.get(f"/api/v1/opportunities?cursor={first_id}", headers=foreign).status_code == 404
    )
