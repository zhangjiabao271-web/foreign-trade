"""All six fixture roles and six states for the two explicit CRM commands."""

from uuid import UUID, uuid4

import pytest
from app.crm.enums import OpportunityStatus
from app.crm.models import Opportunity
from app.identity.enums import MembershipRole
from app.platform.models import IdempotencyKey
from sqlalchemy import func, select
from test_document_review import reviewer
from test_quotation_vertical_slice import create_opportunity, table_counts

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


@pytest.mark.parametrize("role", list(MembershipRole))
@pytest.mark.parametrize(
    "command,allowed_states,target",
    [
        ("start-negotiation", {"QUOTING"}, "NEGOTIATION"),
        ("mark-lost", {"OPEN", "INQUIRY", "QUOTING", "NEGOTIATION"}, "LOST"),
    ],
)
def test_explicit_opportunity_commands_role_state_matrix(
    quotation_fixture, role, command, allowed_states, target
):
    f = quotation_fixture
    subject, context = reviewer(f, role)
    may_write = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.SALES}

    def snapshot(record_id):
        with f.session_factory() as session:
            row = dict(
                session.execute(
                    select(Opportunity.__table__).where(
                        Opportunity.organization_id == f.organization_a,
                        Opportunity.id == record_id,
                    )
                )
                .mappings()
                .one()
            )
            keys = session.scalar(select(func.count()).select_from(IdempotencyKey))
        return row, table_counts(f), keys

    for state in OpportunityStatus:
        _, identifier = create_opportunity(f)
        record_id = UUID(identifier)
        # Isolate each predicate in a fresh record; not a claimed business lifecycle.
        with f.session_factory.begin() as session:
            session.get(Opportunity, record_id).status = state.value
        before, evidence, keys = snapshot(record_id)
        body = {"expected_version": before["version"], "reason": "Synthetic matrix reason"}
        headers = f.headers(subject, f.organization_a) | {"Idempotency-Key": str(uuid4())}
        path = f"/api/v1/opportunities/{record_id}/{command}"
        response = f.client.post(path, headers=headers, json=body)
        after, after_evidence, after_keys = snapshot(record_id)
        if not may_write or state.value not in allowed_states:
            assert response.status_code == (409 if may_write else 403), response.text
            if may_write:
                assert response.json()["code"] == "INVALID_STATE_TRANSITION"
            assert (after, after_evidence, after_keys) == (before, evidence, keys)
            continue
        assert response.status_code == 200, response.text
        assert after["status"] == target
        assert after["version"] == before["version"] + 1
        assert after["updated_by"] == context.user_id
        assert tuple(new - old for old, new in zip(evidence, after_evidence, strict=True)) == (
            1,
            1,
            1,
        )
        assert after_keys == keys + 1
        if target == "LOST":
            assert after["lost_reason"] == body["reason"] and after["lost_at"] is not None
            assert (response.json()["lost_reason"] is None) == (role == MembershipRole.SALES)
        replay = f.client.post(path, headers=headers, json=body)
        assert replay.status_code == 200 and replay.json() == response.json()
        assert snapshot(record_id) == (after, after_evidence, after_keys)
