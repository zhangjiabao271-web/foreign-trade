"""One-time synthetic identity bootstrap; never a production provisioning endpoint."""

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.core.database import create_database_engine, create_session_factory  # noqa: E402
from app.identity.models import Organization, OrganizationMembership, User  # noqa: E402
from app.platform.models import AuditLog, OutboxEvent  # noqa: E402
from app.work.models import Activity  # noqa: E402

SUBJECTS = {
    "manager": "vut537xc2tc5",
    "sales": "zwlpm3e6qz30",
}
ACTION = "acceptance.identity_initialized"


def require_acceptance(settings: Settings) -> None:
    expected = {
        "app_env": "acceptance",
        "database_host": "postgres",
        "database_port": 5432,
        "database_name": "trade_fresh_acceptance",
        "database_user": "rehearsal",
        "oidc_issuer": "http://logto.localhost:3001/oidc",
        "oidc_audience": "https://api.trade-workbench.local",
        "oidc_signing_algorithm": "ES384",
    }
    if any(getattr(settings, key) != value for key, value in expected.items()):
        raise RuntimeError("Refusing identity bootstrap outside the fixed acceptance environment")


def seed(session: Session) -> dict[str, object]:
    # Serialize bootstrap against both another bootstrap and normal identity inserts.
    session.execute(text("LOCK TABLE organizations, users IN SHARE ROW EXCLUSIVE MODE"))
    if session.scalar(select(Organization.id).limit(1)) or session.scalar(select(User.id).limit(1)):
        raise RuntimeError("Identity data already exists; refusing overwrite or additional grants")

    manager = User(external_subject=SUBJECTS["manager"], display_name="本机验收经理")
    sales = User(external_subject=SUBJECTS["sales"], display_name="本机验收销售")
    organization_a = Organization(name="本机验收 A · 非生产", name_normalized="local acceptance a")
    organization_b = Organization(
        name="本机验收 B · 隔离见证", name_normalized="local acceptance b"
    )
    session.add_all([manager, sales, organization_a, organization_b])
    session.flush()
    memberships = [
        OrganizationMembership(
            organization_id=organization_a.id, user_id=manager.id, role="MANAGER", status="ACTIVE"
        ),
        OrganizationMembership(
            organization_id=organization_a.id, user_id=sales.id, role="SALES", status="ACTIVE"
        ),
        OrganizationMembership(
            organization_id=organization_b.id, user_id=manager.id, role="VIEWER", status="ACTIVE"
        ),
    ]
    session.add_all(memberships)
    session.flush()
    correlation_id = uuid4()
    for organization in (organization_a, organization_b):
        bindings = [
            {"user_id": str(row.user_id), "role": row.role, "membership_id": str(row.id)}
            for row in memberships
            if row.organization_id == organization.id
        ]
        # Null actor honestly represents operator-run fixture bootstrap, not a user login.
        session.add_all(
            [
                AuditLog(
                    organization_id=organization.id,
                    action=ACTION,
                    target_type="organization",
                    target_id=organization.id,
                    request_id=correlation_id,
                    correlation_id=correlation_id,
                    after_data={"memberships": bindings},
                    reason=(
                        "User-authorized synthetic identity acceptance bootstrap; "
                        "no production access"
                    ),
                ),
                Activity(
                    organization_id=organization.id,
                    subject_type="organization",
                    subject_id=organization.id,
                    activity_type=ACTION,
                    summary="本机身份验收初始化（非生产）",
                    details={"memberships": bindings},
                    correlation_id=correlation_id,
                ),
                OutboxEvent(
                    organization_id=organization.id,
                    event_type=f"{ACTION}.v1",
                    aggregate_type="organization",
                    aggregate_id=organization.id,
                    payload={"organization_id": str(organization.id)},
                    correlation_id=correlation_id,
                ),
            ]
        )
    session.flush()
    return {
        "organization_a": str(organization_a.id),
        "organization_b": str(organization_b.id),
        "manager_user_id": str(manager.id),
        "sales_user_id": str(sales.id),
        "request_id": str(correlation_id),
        "subjects": SUBJECTS,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-local-identity-fixture", action="store_true", required=True)
    parser.parse_args()
    settings = Settings()
    require_acceptance(settings)
    engine = create_database_engine(settings.database_url)
    try:
        with create_session_factory(engine).begin() as session:
            actual = session.execute(text("SELECT current_database(), current_user")).one()
            if tuple(actual) != ("trade_fresh_acceptance", "rehearsal"):
                raise RuntimeError("Connected database identity does not match acceptance target")
            result = seed(session)
        print(json.dumps(result, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
