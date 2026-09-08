from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError, IntegrityError

ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"
IDENTITY_REVISION = "20260903_0001"
HEAD_REVISION = "20260908_0035"
EXPECTED_TABLES = {
    "ai_disclosures",
    "ai_runs",
    "ai_tool_calls",
    "approval_requests",
    "alembic_version",
    "organizations",
    "users",
    "organization_memberships",
    "document_sequences",
    "audit_logs",
    "outbox_events",
    "async_jobs",
    "idempotency_keys",
    "processed_events",
    "activities",
    "companies",
    "company_roles",
    "contacts",
    "leads",
    "opportunities",
    "products",
    "product_supplier_links",
    "inquiries",
    "quotations",
    "quotation_versions",
    "quotation_items",
    "sales_orders",
    "sales_contracts",
    "expenses",
    "payables",
    "supplier_payments",
    "supplier_payment_allocations",
    "sales_order_items",
    "purchase_orders",
    "purchase_order_items",
    "tasks",
    "shipments",
    "shipment_items",
    "documents",
    "document_versions",
    "document_links",
    "receivables",
    "payments",
    "payment_allocations",
    "customs_declarations",
    "tax_refund_cases",
}
TENANT_TABLES = EXPECTED_TABLES - {"alembic_version", "organizations", "users"}


def alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def insert_identity_fixture(connection: Connection) -> tuple[UUID, UUID, UUID, UUID]:
    organization_a = uuid4()
    organization_b = uuid4()
    user_a = uuid4()
    user_b = uuid4()

    connection.execute(
        text(
            """
            INSERT INTO users (id, external_subject, display_name, email_normalized)
            VALUES (:user_a, :subject_a, 'User A', 'user-a@example.test'),
                   (:user_b, :subject_b, 'User B', 'user-b@example.test')
            """
        ),
        {
            "user_a": user_a,
            "user_b": user_b,
            "subject_a": f"test|{user_a}",
            "subject_b": f"test|{user_b}",
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO organizations (id, name, name_normalized)
            VALUES (:organization_a, 'Organization A', 'organization a'),
                   (:organization_b, 'Organization B', 'organization b')
            """
        ),
        {"organization_a": organization_a, "organization_b": organization_b},
    )
    connection.execute(
        text(
            """
            INSERT INTO organization_memberships
                (organization_id, user_id, role, status)
            VALUES (:organization_a, :user_a, 'ADMIN', 'ACTIVE'),
                   (:organization_b, :user_b, 'ADMIN', 'ACTIVE')
            """
        ),
        {
            "organization_a": organization_a,
            "organization_b": organization_b,
            "user_a": user_a,
            "user_b": user_b,
        },
    )
    return organization_a, organization_b, user_a, user_b


@pytest.mark.integration
def test_empty_database_upgrade_head_and_schema_audit(test_database_url: str) -> None:
    config = alembic_config(test_database_url)
    command.upgrade(config, "head")
    command.check(config)
    engine = create_engine(test_database_url)
    inspector = inspect(engine)

    assert set(inspector.get_table_names()) == EXPECTED_TABLES

    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert revision == HEAD_REVISION

    for table_name in TENANT_TABLES:
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        assert "organization_id" in columns
        for column_name, column in columns.items():
            if column_name.endswith("_at"):
                assert getattr(column["type"], "timezone", False) is True

    membership_uniques = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("organization_memberships")
    }
    assert "uq_organization_memberships_organization_id_user_id" in membership_uniques
    assert "uq_organization_memberships_organization_id_id" in membership_uniques
    membership_indexes = inspector.get_indexes("organization_memberships")
    assert any(
        index["name"] == "ix_memberships_org_created_id"
        and index["column_names"] == ["organization_id", "created_at", "id"]
        for index in membership_indexes
    )

    outbox_indexes = {index["name"] for index in inspector.get_indexes("outbox_events")}
    assert "ix_outbox_events_dispatch" in outbox_indexes
    assert "ix_outbox_events_organization_id_aggregate_type_aggregate_id" in outbox_indexes

    processed_primary_key = inspector.get_pk_constraint("processed_events")
    assert processed_primary_key["constrained_columns"] == [
        "organization_id",
        "event_id",
        "consumer_name",
    ]
    assert any(
        foreign_key["constrained_columns"] == ["organization_id", "event_id"]
        and foreign_key["referred_table"] == "outbox_events"
        for foreign_key in inspector.get_foreign_keys("processed_events")
    )

    async_job_foreign_keys = inspector.get_foreign_keys("async_jobs")
    assert any(
        foreign_key["constrained_columns"] == ["organization_id", "created_by"]
        and foreign_key["referred_table"] == "organization_memberships"
        for foreign_key in async_job_foreign_keys
    )

    version_indexes = {index["name"] for index in inspector.get_indexes("quotation_versions")}
    assert "uq_quotation_versions_current" in version_indexes
    assert "uq_quotation_versions_accepted" in version_indexes
    quotation_foreign_keys = inspector.get_foreign_keys("quotations")
    assert any(
        foreign_key["name"] == "fk_quotations_accepted_version_belongs_to_quotation"
        and foreign_key["constrained_columns"] == ["organization_id", "id", "accepted_version_id"]
        for foreign_key in quotation_foreign_keys
    )
    sales_order_uniques = {
        constraint["name"] for constraint in inspector.get_unique_constraints("sales_orders")
    }
    assert "uq_sales_orders_org_quote" in sales_order_uniques
    purchase_item_foreign_keys = inspector.get_foreign_keys("purchase_order_items")
    assert any(
        foreign_key["constrained_columns"] == ["organization_id", "sales_order_item_id"]
        and foreign_key["referred_table"] == "sales_order_items"
        for foreign_key in purchase_item_foreign_keys
    )
    shipment_item_foreign_keys = inspector.get_foreign_keys("shipment_items")
    assert any(
        foreign_key["constrained_columns"] == ["organization_id", "sales_order_item_id"]
        and foreign_key["referred_table"] == "sales_order_items"
        for foreign_key in shipment_item_foreign_keys
    )
    document_link_indexes = {index["name"] for index in inspector.get_indexes("document_links")}
    assert "ix_document_links_org_target" in document_link_indexes
    engine.dispose()


@pytest.mark.integration
def test_previous_revision_upgrades_to_head_without_losing_identity_data(
    test_database_url: str,
) -> None:
    config = alembic_config(test_database_url)
    command.upgrade(config, IDENTITY_REVISION)
    engine = create_engine(test_database_url)

    with engine.begin() as connection:
        organization_a, _, user_a, _ = insert_identity_fixture(connection)

    command.upgrade(config, "head")

    with engine.connect() as connection:
        membership = connection.execute(
            text(
                """
                SELECT role, status
                FROM organization_memberships
                WHERE organization_id = :organization_id AND user_id = :user_id
                """
            ),
            {"organization_id": organization_a, "user_id": user_a},
        ).one()
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    assert membership == ("ADMIN", "ACTIVE")
    assert revision == HEAD_REVISION
    engine.dispose()


@pytest.mark.integration
def test_cross_tenant_actor_reference_is_rejected_and_audit_is_append_only(
    test_database_url: str,
) -> None:
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)

    with engine.begin() as connection:
        organization_a, _, user_a, user_b = insert_identity_fixture(connection)

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                """
                    INSERT INTO async_jobs
                        (organization_id, created_by, job_type, correlation_id)
                    VALUES (:organization_id, :created_by, 'test.job', :correlation_id)
                    """
            ),
            {
                "organization_id": organization_a,
                "created_by": user_b,
                "correlation_id": uuid4(),
            },
        )

    audit_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO audit_logs
                    (id, organization_id, actor_user_id, action, target_type,
                     request_id, correlation_id)
                VALUES (:id, :organization_id, :actor_user_id, 'fixture.created', 'fixture',
                        :request_id, :correlation_id)
                """
            ),
            {
                "id": audit_id,
                "organization_id": organization_a,
                "actor_user_id": user_a,
                "request_id": uuid4(),
                "correlation_id": uuid4(),
            },
        )

    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(
            text("UPDATE audit_logs SET action = 'fixture.changed' WHERE id = :id"),
            {"id": audit_id},
        )

    with engine.connect() as connection:
        action = connection.execute(
            text("SELECT action FROM audit_logs WHERE id = :id"),
            {"id": audit_id},
        ).scalar_one()
    assert action == "fixture.created"
    engine.dispose()
