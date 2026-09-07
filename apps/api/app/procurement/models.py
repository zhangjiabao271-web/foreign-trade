from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.content_review import ContentReleaseMixin, review_constraint
from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key
from app.core.database_types import exchange_rate_type, money_type, quantity_type


class PurchaseOrder(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        review_constraint("purchase_orders"),
        membership_actor_foreign_key("purchase_orders", "reviewed_by"),
        UniqueConstraint("organization_id", "id", name="uq_purchase_orders_org_id"),
        UniqueConstraint(
            "organization_id", "replaces_purchase_order_id", name="uq_purchase_orders_replacement"
        ),
        ForeignKeyConstraint(
            ["organization_id", "replaces_purchase_order_id"],
            ["purchase_orders.organization_id", "purchase_orders.id"],
            name="fk_purchase_orders_replaces",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "organization_id",
            "purchase_order_number",
            name="uq_purchase_orders_org_number",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'SENT', 'CONFIRMED', 'PARTIALLY_RECEIVED', "
            "'RECEIVED', 'CLOSED', 'CANCELLED')",
            name="ck_purchase_orders_status",
        ),
        CheckConstraint("char_length(currency_code) = 3", name="ck_purchase_orders_currency"),
        CheckConstraint("exchange_rate > 0", name="ck_purchase_orders_rate"),
        CheckConstraint(
            "total >= 0 AND total_order_currency >= 0", name="ck_purchase_orders_totals"
        ),
        ForeignKeyConstraint(
            ["organization_id", "sales_order_id"],
            ["sales_orders.organization_id", "sales_orders.id"],
            name="fk_purchase_orders_org_sales_order",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "supplier_company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_purchase_orders_org_supplier",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "approved_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_purchase_orders_org_approver",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("purchase_orders", "created_by"),
        membership_actor_foreign_key("purchase_orders", "updated_by"),
        Index("ix_purchase_orders_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_purchase_orders_org_sales_order", "organization_id", "sales_order_id"),
        Index(
            "ix_purchase_orders_org_created_id_active",
            "organization_id",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_purchase_orders_org_parent_created_id_active",
            "organization_id",
            "sales_order_id",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    purchase_order_number: Mapped[str] = mapped_column(String(40), nullable=False)
    sales_order_id: Mapped[UUID] = mapped_column(nullable=False)
    supplier_company_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="DRAFT")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(exchange_rate_type(), nullable=False)
    total: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    total_order_currency: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    supplier_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[UUID | None] = mapped_column(nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    replaces_purchase_order_id: Mapped[UUID | None] = mapped_column(nullable=True)


class PurchaseOrderItem(TenantRecordMixin, Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_purchase_order_items_org_id"),
        UniqueConstraint(
            "organization_id",
            "purchase_order_id",
            "line_number",
            name="uq_po_items_line",
        ),
        UniqueConstraint(
            "organization_id",
            "purchase_order_id",
            "sales_order_item_id",
            name="uq_po_items_sales_item",
        ),
        CheckConstraint("line_number > 0", name="ck_purchase_order_items_line"),
        CheckConstraint("quantity > 0", name="ck_purchase_order_items_quantity"),
        CheckConstraint(
            "received_quantity >= 0 AND received_quantity <= quantity",
            name="received_quantity_bounds",
        ),
        CheckConstraint(
            "unit_cost >= 0 AND line_total >= 0", name="ck_purchase_order_items_amounts"
        ),
        ForeignKeyConstraint(
            ["organization_id", "purchase_order_id"],
            ["purchase_orders.organization_id", "purchase_orders.id"],
            name="fk_purchase_order_items_org_order",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "sales_order_item_id"],
            ["sales_order_items.organization_id", "sales_order_items.id"],
            name="fk_purchase_order_items_org_sales_item",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("purchase_order_items", "created_by"),
        membership_actor_foreign_key("purchase_order_items", "updated_by"),
    )

    purchase_order_id: Mapped[UUID] = mapped_column(nullable=False)
    sales_order_item_id: Mapped[UUID] = mapped_column(nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sku_snapshot: Mapped[str] = mapped_column(String(80), nullable=False)
    description_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    unit_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(quantity_type(), nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(
        quantity_type(), nullable=False, server_default="0"
    )
    unit_cost: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
