from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
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


class Quotation(TenantRecordMixin, Base):
    __tablename__ = "quotations"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "quotation_number"),
        UniqueConstraint("organization_id", "inquiry_id"),
        ForeignKeyConstraint(
            ["organization_id", "inquiry_id"],
            ["inquiries.organization_id", "inquiries.id"],
            name="fk_quotations_organization_id_inquiry_id_inquiries",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "opportunity_id"],
            ["opportunities.organization_id", "opportunities.id"],
            name="fk_quotations_organization_id_opportunity_id_opportunities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_quotations_organization_id_company_id_companies",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "id", "accepted_version_id"],
            [
                "quotation_versions.organization_id",
                "quotation_versions.quotation_id",
                "quotation_versions.id",
            ],
            name="fk_quotations_accepted_version_belongs_to_quotation",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        membership_actor_foreign_key("quotations", "created_by"),
        membership_actor_foreign_key("quotations", "updated_by"),
        Index("ix_quotations_organization_id_created_at", "organization_id", "created_at"),
        Index(
            "ix_quotations_org_created_id_active",
            "organization_id",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    quotation_number: Mapped[str] = mapped_column(String(40), nullable=False)
    inquiry_id: Mapped[UUID] = mapped_column(nullable=False)
    opportunity_id: Mapped[UUID] = mapped_column(nullable=False)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    accepted_version_id: Mapped[UUID | None] = mapped_column(nullable=True)


class QuotationVersion(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "quotation_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "quotation_id", "id"),
        UniqueConstraint("organization_id", "quotation_id", "version_number"),
        CheckConstraint("version_number > 0", name="version_number_positive"),
        CheckConstraint(
            "status IN ('DRAFT', 'INTERNAL_REVIEW', 'SENT', 'CUSTOMER_REVIEW', "
            "'ACCEPTED', 'REJECTED', 'EXPIRED', 'SUPERSEDED')",
            name="quotation_version_status",
        ),
        CheckConstraint("char_length(currency_code) = 3", name="currency_code_iso_length"),
        CheckConstraint(
            "char_length(base_currency_code) = 3", name="base_currency_code_iso_length"
        ),
        CheckConstraint("exchange_rate > 0", name="exchange_rate_positive"),
        CheckConstraint(
            "subtotal >= 0 AND total >= 0 AND total_cost >= 0", name="totals_non_negative"
        ),
        ForeignKeyConstraint(
            ["organization_id", "quotation_id"],
            ["quotations.organization_id", "quotations.id"],
            name="fk_quotation_versions_organization_id_quotation_id_quotations",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "approved_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_quotation_versions_organization_id_approved_by_membership",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("quotation_versions", "created_by"),
        membership_actor_foreign_key("quotation_versions", "updated_by"),
        membership_actor_foreign_key("quotation_versions", "reviewed_by"),
        review_constraint("quotation_versions"),
        Index(
            "uq_quotation_versions_current",
            "organization_id",
            "quotation_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index(
            "uq_quotation_versions_accepted",
            "organization_id",
            "quotation_id",
            unique=True,
            postgresql_where=text("status = 'ACCEPTED'"),
        ),
    )

    quotation_id: Mapped[UUID] = mapped_column(nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="DRAFT")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    base_currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(exchange_rate_type(), nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    freight_amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    total: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    gross_profit: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    gross_margin: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[UUID | None] = mapped_column(nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QuotationItem(TenantRecordMixin, Base):
    __tablename__ = "quotation_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "quotation_version_id", "line_number"),
        CheckConstraint("line_number > 0", name="line_number_positive"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0 AND unit_cost >= 0", name="unit_amounts_non_negative"),
        CheckConstraint("cost_exchange_rate > 0", name="cost_exchange_rate_positive"),
        CheckConstraint(
            "tax_amount >= 0 AND freight_amount >= 0 AND allocated_cost >= 0",
            name="item_charges_non_negative",
        ),
        CheckConstraint("char_length(cost_currency) = 3", name="cost_currency_iso_length"),
        ForeignKeyConstraint(
            ["organization_id", "quotation_version_id"],
            ["quotation_versions.organization_id", "quotation_versions.id"],
            name="fk_quotation_items_org_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            name="fk_quotation_items_org_product",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("quotation_items", "created_by"),
        membership_actor_foreign_key("quotation_items", "updated_by"),
    )

    quotation_version_id: Mapped[UUID] = mapped_column(nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    sku_snapshot: Mapped[str] = mapped_column(String(80), nullable=False)
    description_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    unit_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(quantity_type(), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    cost_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    cost_exchange_rate: Mapped[Decimal] = mapped_column(exchange_rate_type(), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    freight_amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    allocated_cost: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    line_subtotal: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    line_cost: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    line_gross_profit: Mapped[Decimal] = mapped_column(money_type(), nullable=False)


class SalesOrder(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "sales_orders"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_sales_orders_org_id"),
        UniqueConstraint("organization_id", "order_number", name="uq_sales_orders_org_number"),
        UniqueConstraint("organization_id", "quotation_id", name="uq_sales_orders_org_quote"),
        CheckConstraint(
            "status IN ('DRAFT', 'CONFIRMED', 'DEPOSIT_PENDING', 'EXECUTING', "
            "'READY_TO_SHIP', 'SHIPPED', 'COMPLETED', 'CANCELLED')",
            name="ck_sales_orders_status",
        ),
        CheckConstraint("char_length(currency_code) = 3", name="ck_sales_orders_currency"),
        CheckConstraint(
            "char_length(base_currency_code) = 3", name="ck_sales_orders_base_currency"
        ),
        CheckConstraint("exchange_rate > 0", name="ck_sales_orders_exchange_rate"),
        CheckConstraint(
            "deposit_rate >= 0 AND deposit_rate <= 1", name="ck_sales_orders_deposit_rate"
        ),
        CheckConstraint(
            "subtotal >= 0 AND total >= 0 AND total_cost >= 0 AND deposit_amount >= 0",
            name="ck_sales_orders_totals",
        ),
        ForeignKeyConstraint(
            ["organization_id", "quotation_id"],
            ["quotations.organization_id", "quotations.id"],
            name="fk_sales_orders_org_quotation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "quotation_id", "quotation_version_id"],
            [
                "quotation_versions.organization_id",
                "quotation_versions.quotation_id",
                "quotation_versions.id",
            ],
            name="fk_sales_orders_org_quotation_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_sales_orders_org_company",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("sales_orders", "created_by"),
        membership_actor_foreign_key("sales_orders", "updated_by"),
        membership_actor_foreign_key("sales_orders", "reviewed_by"),
        review_constraint("sales_orders"),
        Index("ix_sales_orders_org_status_created", "organization_id", "status", "created_at"),
        Index(
            "ix_sales_orders_org_created_id_active",
            "organization_id",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    order_number: Mapped[str] = mapped_column(String(40), nullable=False)
    quotation_id: Mapped[UUID] = mapped_column(nullable=False)
    quotation_version_id: Mapped[UUID] = mapped_column(nullable=False)
    opportunity_id: Mapped[UUID] = mapped_column(nullable=False)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="DRAFT")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    base_currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(exchange_rate_type(), nullable=False)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    freight_amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    total: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    total_cost: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    gross_profit: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    gross_margin: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    deposit_rate: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    deposit_amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    deposit_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SalesOrderItem(TenantRecordMixin, Base):
    __tablename__ = "sales_order_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_sales_order_items_org_id"),
        UniqueConstraint(
            "organization_id",
            "sales_order_id",
            "line_number",
            name="uq_sales_order_items_line",
        ),
        UniqueConstraint(
            "organization_id",
            "sales_order_id",
            "quotation_item_id",
            name="uq_sales_order_items_quote_item",
        ),
        CheckConstraint("line_number > 0", name="ck_sales_order_items_line"),
        CheckConstraint("quantity > 0", name="ck_sales_order_items_quantity"),
        CheckConstraint(
            "unit_price >= 0 AND unit_cost >= 0 AND line_total >= 0 AND line_cost >= 0",
            name="ck_sales_order_items_amounts",
        ),
        CheckConstraint("cost_exchange_rate > 0", name="ck_sales_order_items_rate"),
        CheckConstraint("char_length(cost_currency) = 3", name="ck_sales_order_items_currency"),
        ForeignKeyConstraint(
            ["organization_id", "sales_order_id"],
            ["sales_orders.organization_id", "sales_orders.id"],
            name="fk_sales_order_items_org_order",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "quotation_item_id"],
            ["quotation_items.organization_id", "quotation_items.id"],
            name="fk_sales_order_items_org_quote_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            name="fk_sales_order_items_org_product",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("sales_order_items", "created_by"),
        membership_actor_foreign_key("sales_order_items", "updated_by"),
    )

    sales_order_id: Mapped[UUID] = mapped_column(nullable=False)
    quotation_item_id: Mapped[UUID] = mapped_column(nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    sku_snapshot: Mapped[str] = mapped_column(String(80), nullable=False)
    description_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    unit_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(quantity_type(), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    cost_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    cost_exchange_rate: Mapped[Decimal] = mapped_column(exchange_rate_type(), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    freight_amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    allocated_cost: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    line_subtotal: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    line_cost: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    line_gross_profit: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
