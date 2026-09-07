import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app.core.config import Settings  # noqa: E402
from app.identity.models import Organization, OrganizationMembership, User  # noqa: E402
from app.platform.models import AuditLog, OutboxEvent  # noqa: E402
from app.work.models import Activity  # noqa: E402
from identity_acceptance_fixture import SUBJECTS, require_acceptance, seed  # noqa: E402


def acceptance_settings(**overrides):
    values = dict(
        app_env="acceptance",
        database_host="postgres",
        database_port=5432,
        database_name="trade_fresh_acceptance",
        database_user="rehearsal",
        oidc_issuer="http://logto.localhost:3001/oidc",
        oidc_audience="https://api.trade-workbench.local",
        oidc_signing_algorithm="ES384",
    )
    return Settings(**(values | overrides))


def test_exact_target_allowed():
    require_acceptance(acceptance_settings())


@pytest.mark.parametrize(
    "override",
    [
        {"app_env": "production"},
        {"database_host": "localhost"},
        {"database_port": 25432},
        {"database_name": "trade_workbench"},
        {"database_user": "trade_workbench"},
        {"oidc_issuer": "https://other.example/oidc"},
        {"oidc_audience": "other"},
        {"oidc_signing_algorithm": "RS256"},
    ],
)
def test_other_targets_rejected(override):
    with pytest.raises(RuntimeError, match="fixed acceptance"):
        require_acceptance(acceptance_settings(**override))


@pytest.fixture
def identity_factory(test_database_url):
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", test_database_url.replace("%", "%%"))
    command.upgrade(config, "head")
    engine = create_engine(test_database_url)
    try:
        yield sessionmaker(engine)
    finally:
        engine.dispose()


def test_seed_exact_roles_evidence_and_repeat_refusal(identity_factory):
    with identity_factory.begin() as session:
        result = seed(session)
    with identity_factory() as session:
        assert session.scalar(select(func.count()).select_from(Organization)) == 2
        assert set(session.scalars(select(User.external_subject))) == set(SUBJECTS.values())
        roles = list(session.scalars(select(OrganizationMembership.role)))
        assert sorted(roles) == ["MANAGER", "SALES", "VIEWER"]
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 2
        assert session.scalar(select(func.count()).select_from(Activity)) == 2
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 2
        assert all(row.actor_user_id is None for row in session.scalars(select(AuditLog)))
        original_ids = set(session.scalars(select(OrganizationMembership.id)))
        assert result["organization_a"] != result["organization_b"]
    with pytest.raises(RuntimeError, match="already exists"), identity_factory.begin() as session:
        seed(session)
    with identity_factory() as session:
        assert set(session.scalars(select(OrganizationMembership.id))) == original_ids


@pytest.mark.parametrize("record", [Activity, AuditLog, OutboxEvent])
def test_evidence_failure_rolls_back_all_identity_facts(identity_factory, record):
    def fail(*_args):
        raise RuntimeError("injected evidence failure")

    event.listen(record, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"), identity_factory.begin() as session:
            seed(session)
    finally:
        event.remove(record, "before_insert", fail)
    with identity_factory() as session:
        for model in [User, Organization, OrganizationMembership, Activity, AuditLog, OutboxEvent]:
            assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("existing", ["user", "organization"])
def test_partial_existing_identity_is_preserved(identity_factory, existing):
    with identity_factory.begin() as session:
        row = (
            User(external_subject="existing-subject", display_name="Existing")
            if existing == "user"
            else Organization(name="Existing", name_normalized="existing")
        )
        session.add(row)
        session.flush()
        original_id = row.id
    with pytest.raises(RuntimeError, match="already exists"), identity_factory.begin() as session:
        seed(session)
    with identity_factory() as session:
        assert session.scalar(select(type(row).id)) == original_id
        assert session.scalar(select(func.count()).select_from(OrganizationMembership)) == 0
