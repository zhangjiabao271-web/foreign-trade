# Catalog

V1 products are organization-owned reusable defaults, not historical commercial facts. A
product stores SKU, description, unit, standard cost and its ISO 4217 cost currency. Every
quotation item copies these values into an immutable version snapshot, so later catalog edits
cannot change an existing quotation.

All reads and writes require `organization_id`; SKU is unique per active organization. Decimal
values are never converted to float.

Product list responses retain page-local count and add has_more/next_cursor. Cursor anchors
are active products looked up within the current organization, ordered by name then UUID;
foreign/deleted anchors return 404. Search treats percent/underscore/backslash literally.
Limit is 1–100, default 50; each page reads at most limit+1 rows. Index 0023 supports the
active organization/name/id ordering and has a data-preserving downgrade. Read navigation
does not write audit/outbox; existing create commands and commercial snapshots are unchanged.
This is live navigation, not an immutable export snapshot; restart if an anchor is removed.

## Product supplier references

Migration 0016 adds `product_supplier_links`, one active reference per organization/product/supplier.
Composite foreign keys protect both product and company relationships. Reference terms include
supplier SKU, NUMERIC(18,4) unit price, uppercase currency, integer lead time in days, quotation
date/validity and source reference. Unit price is per the product's unit; it is not a purchase order,
supplier acceptance or an automatic product-cost/quotation update. No delete or identity move exists.

Create/update commands have durable idempotency keys; updates require opening version and reason.
Company-first locking, supplier-role validation and refreshed locked reads protect concurrent edits.
Activities, full before/after audit and ID-only outbox events commit atomically. History is bounded;
supplier names are batch-read, not queried per row. Downgrade refuses a nonempty reference table.

ADR-020 supersedes the earlier role policy. Product query services return detached response
projections: standard_cost/cost_currency are null without profit.read. Underlying Product facts
remain intact for backend quotation snapshots; no migration or zero-cost backfill is performed.
Cost-bearing product creation requires both product.write and profit.read at API/service layers.

`product_supplier.read` is granted to ADMIN/MANAGER/FINANCE; `product_supplier.write` and
product.write are limited to existing ADMIN/MANAGER authors. SALES/OPERATIONS lose those
cost-bearing permissions but retain product.read. All supplier read/history/write/replay
service boundaries and API dependencies additionally require profit.read. FINANCE visibility
does not grant write rights. V1 /products keeps the ordinary product directory/basic details
available without mounting protected supplier queries. Privileged exact price maintenance and
historical snapshot invariance remain unchanged.
See V1_STATUS for tested evidence and remaining whole-system acceptance work.

ADR-020 / 0029 additionally protects Product.description via detached query and creation DTOs.
Name/SKU/unit remain identifiers (cost/profit entry forbidden). product.read plus profit.read
allows GET/POST products/{record_id}/text-review, independently binding original description
and record version. Review never changes product cost or grants supplier-write authority.
Original description remains available to backend snapshot copying, not to unauthorized readers.
No downstream quotation/order/contract inherits this disclosure review. Populated downgrade fails.
