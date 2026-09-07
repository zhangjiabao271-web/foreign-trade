from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.crm.models import Opportunity
from app.identity.models import Organization
from app.sales import services
from app.sales.models import Quotation, QuotationVersion
from sqlalchemy import select
from test_quotation_vertical_slice import (
    create_commercial_inputs,
    post_ok,
    post_state,
    table_counts,
)

pytest_plugins = ("test_quotation_vertical_slice",)


def freeze(monkeypatch, instant):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    monkeypatch.setattr(services, "datetime", Clock)


def sent_quote(f, timezone, review=False):
    with f.session_factory.begin() as session:
        session.get(Organization, f.organization_a).timezone = timezone
    data, _, opportunity_id = create_commercial_inputs(f)
    data["valid_until"] = "2026-09-06"
    quote = post_ok(f, "/api/v1/quotations", "quotation-manager", data, 201)
    for action, subject in (
        ("submit", "quotation-sales"),
        ("approve", "quotation-manager"),
        ("send", "quotation-sales"),
    ):
        post_ok(f, f"/api/v1/quotations/{quote['id']}/{action}", subject)
    if review:
        response = f.client.post(
            f"/api/v1/quotations/{quote['id']}/mark-customer-review",
            headers=f.headers("quotation-sales", f.organization_a)
            | {"Idempotency-Key": "validity-review"},
            json={
                "expected_version_id": quote["current_version"]["id"],
                "reason": "Customer started review",
            },
        )
        assert response.status_code == 200
    return quote, opportunity_id


@pytest.mark.parametrize(
    "timezone,instant,allowed",
    [
        ("Asia/Shanghai", "2026-09-06T15:59:59.999999+00:00", True),
        ("Asia/Shanghai", "2026-09-06T16:00:00+00:00", False),
        ("America/Los_Angeles", "2026-09-07T06:59:59.999999+00:00", True),
        ("America/Los_Angeles", "2026-09-07T07:00:00+00:00", False),
        ("UTC", "2026-09-06T23:59:59.999999+00:00", True),
        ("UTC", "2026-09-07T00:00:00+00:00", False),
    ],
)
@pytest.mark.parametrize("review", [False, True])
def test_acceptance_uses_organization_midnight_without_partial_writes(
    quotation_fixture, monkeypatch, timezone, instant, allowed, review
):
    f = quotation_fixture
    quote, opportunity_id = sent_quote(f, timezone, review)
    before = table_counts(f)
    moment = datetime.fromisoformat(instant)
    freeze(monkeypatch, moment)
    response = post_state(
        f,
        f"/api/v1/quotations/{quote['id']}/accept",
    )
    if allowed:
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ACCEPTED"
        assert datetime.fromisoformat(response.json()["accepted_at"]) == moment
        # Acceptance and CRM's WON transition each write their own evidence atomically.
        assert table_counts(f) == tuple(count + 2 for count in before)
    else:
        assert response.status_code == 409
        assert response.json()["code"] == "QUOTATION_VALIDITY_ENDED"
        assert table_counts(f) == before
        with f.session_factory() as session:
            assert session.get(Quotation, UUID(quote["id"])).accepted_version_id is None
            version = session.get(QuotationVersion, UUID(quote["current_version"]["id"]))
            assert version.status == ("CUSTOMER_REVIEW" if review else "SENT")
            assert version.accepted_at is None
            opportunity = session.scalar(
                select(Opportunity).where(Opportunity.id == opportunity_id)
            )
            assert opportunity.status != "WON"


def test_accepted_retry_and_order_creation_survive_later_deadline(quotation_fixture, monkeypatch):
    f = quotation_fixture
    quote, _ = sent_quote(f, "Asia/Shanghai")
    freeze(monkeypatch, datetime(2026, 9, 6, 15, tzinfo=UTC))
    accepted = post_ok(f, f"/api/v1/quotations/{quote['id']}/accept", "quotation-sales")
    before = table_counts(f)
    freeze(monkeypatch, datetime(2027, 1, 1, tzinfo=UTC))
    assert post_ok(f, f"/api/v1/quotations/{quote['id']}/accept", "quotation-sales") == accepted
    assert table_counts(f) == before
    order = post_ok(
        f, "/api/v1/sales-orders", "quotation-sales", {"quotation_id": quote["id"]}, 201
    )
    assert order["quotation_version_id"] == accepted["id"]


def test_expired_quote_can_only_be_renewed_by_new_approved_version(quotation_fixture, monkeypatch):
    f = quotation_fixture
    quote, _ = sent_quote(f, "UTC")
    freeze(monkeypatch, datetime(2026, 9, 7, tzinfo=UTC))
    path = f"/api/v1/quotations/{quote['id']}"
    assert post_state(f, path + "/accept").status_code == 409
    revision = post_ok(
        f, path + "/revisions", "quotation-sales", {"valid_until": "2026-09-10"}, 201
    )
    assert revision["id"] != quote["current_version"]["id"]
    assert post_state(f, path + "/accept").status_code == 409
    for action, subject in (
        ("submit", "quotation-sales"),
        ("approve", "quotation-manager"),
        ("send", "quotation-sales"),
    ):
        post_ok(f, path + "/" + action, subject)
    assert post_ok(f, path + "/accept", "quotation-sales")["id"] == revision["id"]
    with f.session_factory() as session:
        old = session.get(QuotationVersion, UUID(quote["current_version"]["id"]))
        assert old.valid_until.isoformat() == "2026-09-06"
        assert old.status == "SUPERSEDED"
