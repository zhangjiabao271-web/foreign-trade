from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key
from app.core.database_types import quantity_type


class Shipment(TenantRecordMixin, Base):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_shipments_org_id"),
        UniqueConstraint("organization_id", "shipment_number", name="uq_shipments_org_number"),
        CheckConstraint(
            "status IN ('PLANNING', 'BOOKED', 'READY', 'CUSTOMS', 'DEPARTED', "
            "'IN_TRANSIT', 'ARRIVED', 'DELIVERED')",
            name="ck_shipments_status",
        ),
        ForeignKeyConstraint(
            ["organization_id", "forwarder_company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_shipments_org_forwarder",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("shipments", "created_by"),
        membership_actor_foreign_key("shipments", "updated_by"),
        Index("ix_shipments_org_status_created", "organization_id", "status", "created_at"),
        Index(
            "ix_shipments_org_created_id_active",
            "organization_id",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    shipment_number: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PLANNING")
    forwarder_company_id: Mapped[UUID | None] = mapped_column(nullable=True)
    booking_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    planned_departure_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_arrival_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    customs_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    in_transit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ShipmentItem(TenantRecordMixin, Base):
    __tablename__ = "shipment_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_shipment_items_org_id"),
        UniqueConstraint(
            "organization_id", "shipment_id", "sales_order_item_id", name="uq_shipment_items_line"
        ),
        CheckConstraint("quantity > 0", name="ck_shipment_items_quantity"),
        ForeignKeyConstraint(
            ["organization_id", "shipment_id"],
            ["shipments.organization_id", "shipments.id"],
            name="fk_shipment_items_org_shipment",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "sales_order_item_id"],
            ["sales_order_items.organization_id", "sales_order_items.id"],
            name="fk_shipment_items_org_sales_item",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("shipment_items", "created_by"),
        membership_actor_foreign_key("shipment_items", "updated_by"),
        Index("ix_shipment_items_org_sales_item", "organization_id", "sales_order_item_id"),
    )

    shipment_id: Mapped[UUID] = mapped_column(nullable=False)
    sales_order_item_id: Mapped[UUID] = mapped_column(nullable=False)
    quantity: Mapped[Decimal] = mapped_column(quantity_type(), nullable=False)
