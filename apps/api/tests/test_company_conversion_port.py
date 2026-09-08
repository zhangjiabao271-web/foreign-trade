from dataclasses import replace
from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.lead_conversion import ConversionSource, resolve_conversion_parties
from app.companies.models import Company, CompanyRole, Contact
from app.crm.models import Lead, Opportunity
from app.crm.services import LeadCommandService
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_crm_acceptance_matrix import responded

pytest_plugins = ("test_crm_vertical_slice",)

SOURCE = ConversionSource(
    company_name="Northwind Marine",
    country_code="CN",
    contact_name="Ada Zhou",
    email="Ada@Northwind.Example",
    email_normalized="ada@northwind.example",
    phone="+86 138 0000 0000",
)


def context(f):
    return RequestContext(
        user_id=f.user_a,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.LEAD_CONVERT}),
        request_id=uuid4(),
    )


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(
                session.execute(select(*model.__table__.columns).order_by(model.id))
            )
            for model in (
                Company,
                CompanyRole,
                Contact,
                Lead,
                Opportunity,
                Activity,
                AuditLog,
                OutboxEvent,
            )
        }


def test_port_requires_originating_permission_before_database_access():
    ctx = RequestContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        request_id=uuid4(),
        permissions=frozenset(Permission) - {Permission.LEAD_CONVERT},
    )
    with Session() as session:
        with pytest.raises(ApiProblem) as error:
            resolve_conversion_parties(session, ctx, SOURCE)
        assert error.value.code == "PERMISSION_DENIED"
        assert not session.new and not session.dirty
        assert not session.in_transaction()


@pytest.mark.integration
def test_port_keeps_same_name_companies_in_separate_tenants(crm_fixture):
    f = crm_fixture
    with f.session_factory.begin() as session:
        foreign = Company(
            organization_id=f.organization_b,
            name=SOURCE.company_name,
            name_normalized="northwind marine",
            country_code="US",
        )
        session.add(foreign)
        session.flush()
        foreign_id = foreign.id
    before = snapshot(f)
    with f.session_factory.begin() as session:
        result = resolve_conversion_parties(session, context(f), SOURCE)
        assert result.company_id != foreign_id
    after = snapshot(f)
    assert before["companies"][0] in after["companies"]
    with f.session_factory() as session:
        company = session.get(Company, result.company_id)
        contact = session.get(Contact, result.contact_id)
        assert company.organization_id == contact.organization_id == f.organization_a
        assert company.country_code == "CN"
        assert contact.company_id == company.id
    for table in ("activities", "audit_logs", "outbox_events", "leads", "opportunities"):
        assert after[table] == before[table]


@pytest.mark.integration
@pytest.mark.parametrize("existing_company", [False, True])
def test_caller_failure_rolls_back_all_port_writes(crm_fixture, existing_company):
    f = crm_fixture
    if existing_company:
        with f.session_factory.begin() as session:
            session.add(
                Company(
                    organization_id=f.organization_a,
                    name="NORTHWIND MARINE",
                    name_normalized="northwind marine",
                    country_code="US",
                )
            )
    before = snapshot(f)
    with (
        pytest.raises(RuntimeError, match="caller failed"),
        f.session_factory.begin() as session,
    ):
        result = resolve_conversion_parties(session, context(f), SOURCE)
        assert session.get(Contact, result.contact_id) is not None
        raise RuntimeError("caller failed after owner flush")
    assert snapshot(f) == before


@pytest.mark.integration
def test_conversion_preserves_existing_company_source_contact_and_replay(crm_fixture):
    f = crm_fixture
    lead_id = responded(f)
    with f.session_factory.begin() as session:
        company = Company(
            organization_id=f.organization_a,
            name="NORTHWIND MARINE",
            name_normalized="northwind marine",
            country_code="US",
        )
        session.add(company)
        session.flush()
        company_id = company.id
    before = snapshot(f)
    service = LeadCommandService(f.session_factory)
    result = service.convert(context(f), lead_id)
    assert result[1] == company_id
    after = snapshot(f)
    assert after["companies"] == before["companies"]
    with f.session_factory() as session:
        contact = session.get(Contact, result[2])
        assert (contact.full_name, contact.email, contact.email_normalized, contact.phone) == (
            SOURCE.contact_name,
            SOURCE.email,
            SOURCE.email_normalized,
            SOURCE.phone,
        )
        assert session.get(Lead, lead_id).source == "trade-fair"
    assert service.convert(context(f), lead_id)[1:] == result[1:]
    assert snapshot(f) == after


@pytest.mark.integration
def test_crm_calls_owner_port_and_rolls_back_after_its_flush(crm_fixture, monkeypatch):
    f = crm_fixture
    lead_id = responded(f)
    before = snapshot(f)
    calls = []

    def fail_after_owner(session, ctx, source):
        assert source == SOURCE
        calls.append(resolve_conversion_parties(session, ctx, source))
        raise RuntimeError("owner returned then caller failed")

    monkeypatch.setattr("app.crm.services.resolve_conversion_parties", fail_after_owner)
    with pytest.raises(RuntimeError, match="owner returned"):
        LeadCommandService(f.session_factory).convert(context(f), lead_id)
    assert len(calls) == 1
    assert snapshot(f) == before


@pytest.mark.integration
def test_port_retains_company_name_as_missing_contact_name_fallback(crm_fixture):
    f = crm_fixture
    with f.session_factory.begin() as session:
        result = resolve_conversion_parties(session, context(f), replace(SOURCE, contact_name=None))
        assert session.get(Contact, result.contact_id).full_name == SOURCE.company_name
