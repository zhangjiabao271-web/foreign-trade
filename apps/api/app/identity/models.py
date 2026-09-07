from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy import Uuid as SQLAlchemyUuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin, VersionMixin
from app.identity.enums import MembershipStatus, OrganizationStatus, UserStatus


class User(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("external_subject"),
        CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="user_status"),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_users_email_normalized", "email_normalized"),
    )

    external_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_normalized: Mapped[str | None] = mapped_column(String(320), nullable=True)
    status: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )
    created_by: Mapped[UUID | None] = mapped_column(
        SQLAlchemyUuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        SQLAlchemyUuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="organization_status"),
        CheckConstraint("version > 0", name="version_positive"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Shanghai",
        server_default="Asia/Shanghai",
    )
    status: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default=OrganizationStatus.ACTIVE,
        server_default=OrganizationStatus.ACTIVE.value,
    )
    created_by: Mapped[UUID | None] = mapped_column(
        SQLAlchemyUuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        SQLAlchemyUuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OrganizationMembership(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "user_id"),
        CheckConstraint(
            "role IN ('ADMIN', 'MANAGER', 'SALES', 'OPERATIONS', 'FINANCE', 'VIEWER')",
            name="membership_role",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'INVITED', 'DISABLED')",
            name="membership_status",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_organization_memberships_user_id_status", "user_id", "status"),
        Index("ix_organization_memberships_organization_id_status", "organization_id", "status"),
        Index("ix_memberships_org_created_id", "organization_id", "created_at", "id"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        SQLAlchemyUuid,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        SQLAlchemyUuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default=MembershipStatus.INVITED,
        server_default=MembershipStatus.INVITED.value,
    )
    created_by: Mapped[UUID | None] = mapped_column(
        SQLAlchemyUuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        SQLAlchemyUuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
