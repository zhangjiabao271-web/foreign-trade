"""CRM port predicates and caller transaction ownership, with synthetic evidence IDs."""

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.crm.enums import OpportunityStatus
from app.crm.models import Opportunity
from app.crm.opportunity_services import advance_from_evidence
from sqlalchemy import select
from test_document_review import reviewer
from test_quotation_vertical_slice import create_opportunity, table_counts

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


@pytest.mark.parametrize(
    "source,permission,allowed,target",
    [
        ("inquiry", Permission.INQUIRY_WRITE, {"OPEN", "INQUIRY"}, "INQUIRY"),
        ("quotation", Permission.QUOTATION_WRITE, {"INQUIRY", "QUOTING"}, "QUOTING"),
        ("accepted", Permission.QUOTATION_ACCEPT, {"QUOTING", "NEGOTIATION"}, "WON"),
    ],
)
def test_evidence_port_states_authority_and_caller_rollback(
    quotation_fixture, source, permission, allowed, target
):
    f = quotation_fixture
    _, context = reviewer(f)

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
        return row, table_counts(f)

    for state in OpportunityStatus:
        _, identifier = create_opportunity(f)
        record_id, evidence_id = UUID(identifier), uuid4()
        with f.session_factory.begin() as session:
            session.get(Opportunity, record_id).status = state.value
        before, counts = snapshot(record_id)

        def advance(session, actor=context, current_id=record_id, current_evidence=evidence_id):
            return advance_from_evidence(
                session, actor, current_id, event=source, evidence_id=current_evidence
            )

        # Originating permission is independently necessary, even for an otherwise valid user.
        with pytest.raises(ApiProblem) as denied, f.session_factory.begin() as session:
            advance(session, replace(context, permissions=context.permissions - {permission}))
        assert denied.value.status == 403
        assert snapshot(record_id) == (before, counts)
        with pytest.raises(ApiProblem) as foreign, f.session_factory.begin() as session:
            advance(session, replace(context, organization_id=f.organization_b))
        assert foreign.value.status == 404
        assert snapshot(record_id) == (before, counts)

        if state.value not in allowed:
            with pytest.raises(ApiProblem) as invalid, f.session_factory.begin() as session:
                advance(session)
            assert invalid.value.status == 409
            assert invalid.value.code == "INVALID_STATE_TRANSITION"
            assert snapshot(record_id) == (before, counts)
            continue

        # An error after the port returns must undo its flushed state and all three receipts.
        with (
            pytest.raises(RuntimeError, match="caller failed"),
            f.session_factory.begin() as session,
        ):
            assert advance(session).status == target
            raise RuntimeError("caller failed")
        assert snapshot(record_id) == (before, counts)
        with f.session_factory.begin() as session:
            assert advance(session).status == target
        after, after_counts = snapshot(record_id)
        changed = int(state.value != target)
        assert after["version"] == before["version"] + changed
        assert (
            tuple(new - old for old, new in zip(counts, after_counts, strict=True))
            == (changed,) * 3
        )
        if changed:
            assert after["updated_by"] == context.user_id
        else:
            assert after == before
