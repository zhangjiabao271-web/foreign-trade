from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Engine,
    ForeignKey,
    ForeignKeyConstraint,
    MetaData,
    Uuid,
    create_engine,
    func,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    declared_attr,
    mapped_column,
    sessionmaker,
)

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class VersionMixin:
    version: Mapped[int] = mapped_column(nullable=False, server_default=text("1"))

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, object]:
        return {"version_id_col": cls.version}


class TenantRecordMixin(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin):
    organization_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    updated_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def membership_actor_foreign_key(
    table_name: str,
    actor_column: str,
) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", actor_column],
        ["organization_memberships.organization_id", "organization_memberships.user_id"],
        name=f"fk_{table_name}_organization_id_{actor_column}_membership",
        ondelete="RESTRICT",
    )


def create_database_engine(database_url: str | None = None) -> Engine:
    return create_engine(database_url or get_settings().database_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
