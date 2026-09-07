from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.content_review import ContentReleaseMixin, review_constraint
from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key
from app.core.database_types import money_type


class Product(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        Index(
            "uq_products_organization_id_sku_active",
            "organization_id",
            "sku",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("standard_cost >= 0", name="standard_cost_non_negative"),
        Index(
            "ix_products_org_name_id_active",
            "organization_id",
            "name",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("char_length(cost_currency) = 3", name="cost_currency_iso_length"),
        membership_actor_foreign_key("products", "created_by"),
        membership_actor_foreign_key("products", "updated_by"),
        membership_actor_foreign_key("products", "reviewed_by"),
        review_constraint("products"),
    )

    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    standard_cost: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    cost_currency: Mapped[str] = mapped_column(String(3), nullable=False)


class ProductSupplierLink(TenantRecordMixin, Base):
    __tablename__ = "product_supplier_links"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        Index(
            "uq_product_supplier_links_org_product_supplier_active",
            "organization_id",
            "product_id",
            "supplier_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_product_supplier_links_org_product_created",
            "organization_id",
            "product_id",
            "created_at",
            "id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["companies.organization_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("unit_price >= 0", name="supplier_price_non_negative"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="supplier_currency_format"),
        CheckConstraint(
            "lead_time_days >= 0 AND lead_time_days <= 3650", name="supplier_lead_time_range"
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_until >= quoted_on", name="supplier_quote_date_order"
        ),
        membership_actor_foreign_key("product_supplier_links", "created_by"),
        membership_actor_foreign_key("product_supplier_links", "updated_by"),
    )
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    supplier_id: Mapped[UUID] = mapped_column(nullable=False)
    supplier_sku: Mapped[str] = mapped_column(String(80), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    lead_time_days: Mapped[int] = mapped_column(nullable=False)
    quoted_on: Mapped[date] = mapped_column(nullable=False)
    valid_until: Mapped[date | None] = mapped_column(nullable=True)
    quotation_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
