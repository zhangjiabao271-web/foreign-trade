from uuid import UUID, uuid4

import pytest
from alembic import command
from app.companies.models import Company
from app.crm.models import Lead, Opportunity
from legacy_migration import assert_snapshot, legacy_snapshot
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from test_order_procurement_vertical_slice import create_confirmed_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)

CONSTRAINT = "fk_sales_orders_org_opportunity"


def test_order_rejects_foreign_and_missing_opportunity_without_changing_snapshot(quotation_fixture):
    fixture = quotation_fixture
    order, _, _ = create_confirmed_order(fixture)
    with fixture.session_factory.begin() as session:
        company = Company(
            organization_id=fixture.organization_b,
            name="Foreign relationship fixture",
            name_normalized="foreign relationship fixture",
        )
        lead = Lead(organization_id=fixture.organization_b, company_name=company.name)
        session.add_all([company, lead])
        session.flush()
        opportunity = Opportunity(
            organization_id=fixture.organization_b,
            company_id=company.id,
            source_lead_id=lead.id,
            name="Foreign opportunity fixture",
        )
        session.add(opportunity)
        session.flush()
        foreign_id = opportunity.id

    params = {"org": fixture.organization_a, "id": UUID(order["id"])}
    read = text("SELECT * FROM sales_orders WHERE organization_id=:org AND id=:id")
    with fixture.engine.connect() as connection:
        original = dict(connection.execute(read, params).mappings().one())
    for invalid_id in (foreign_id, uuid4()):
        with pytest.raises(IntegrityError) as denied, fixture.engine.begin() as connection:
            connection.execute(
                text("""
                    UPDATE sales_orders SET opportunity_id=:opportunity
                    WHERE organization_id=:org AND id=:id
                """),
                params | {"opportunity": invalid_id},
            )
        assert denied.value.orig.sqlstate == "23503"
        assert denied.value.orig.diag.constraint_name == CONSTRAINT
        with fixture.engine.connect() as connection:
            assert dict(connection.execute(read, params).mappings().one()) == original


def test_order_opportunity_constraint_upgrade_and_rollback_preserve_all_facts(quotation_fixture):
    create_confirmed_order(quotation_fixture)
    with legacy_snapshot(quotation_fixture.engine, "20260907_0033") as (
        config,
        target,
        metadata,
        expected,
    ):
        command.upgrade(config, "head")
        command.check(config)
        assert_snapshot(target, metadata, expected)
        assert any(
            fk["name"] == CONSTRAINT
            and fk["constrained_columns"] == ["organization_id", "opportunity_id"]
            and fk["referred_columns"] == ["organization_id", "id"]
            and fk["referred_table"] == "opportunities"
            for fk in inspect(target).get_foreign_keys("sales_orders")
        )
        command.downgrade(config, "20260907_0033")
        assert_snapshot(target, metadata, expected)
        assert CONSTRAINT not in {
            fk["name"] for fk in inspect(target).get_foreign_keys("sales_orders")
        }
        command.upgrade(config, "head")
        command.check(config)
        assert_snapshot(target, metadata, expected)


def test_invalid_legacy_order_reference_stops_upgrade_without_rewriting_evidence(quotation_fixture):
    order, _, _ = create_confirmed_order(quotation_fixture)
    with legacy_snapshot(quotation_fixture.engine, "20260907_0033") as (
        config,
        target,
        metadata,
        expected,
    ):
        invalid_id = uuid4()
        with target.begin() as connection:
            connection.execute(
                text("""
                    UPDATE sales_orders SET opportunity_id=:opportunity
                    WHERE organization_id=:org AND id=:id
                """),
                {
                    "org": quotation_fixture.organization_a,
                    "id": UUID(order["id"]),
                    "opportunity": invalid_id,
                },
            )
        for row in expected["sales_orders"]:
            if row["id"] == UUID(order["id"]):
                row["opportunity_id"] = invalid_id
        with pytest.raises(IntegrityError) as denied:
            command.upgrade(config, "head")
        assert denied.value.orig.sqlstate == "23503"
        assert denied.value.orig.diag.constraint_name == CONSTRAINT
        assert_snapshot(target, metadata, expected)
        with target.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "20260907_0033"
            )
