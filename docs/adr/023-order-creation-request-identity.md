# ADR-023: Sales-order creation request identity

Status: Accepted for the authorized unreleased V1 implementation, 2026-09-07.

## Problem

The quotation lock and unique order/quotation constraint prevent duplicate orders, but the
existing-order branch silently accepts a different deposit rate or due date. This can report
success for commercial conditions that were never stored. There is no durable request receipt.

## Decision

Creation accepts an optional Idempotency-Key at HTTP/service boundaries. Missing keys remain
fresh requests for compatibility. The service validates a copied SalesOrderCreate payload and
normalizes the deposit rate to the existing four-place precision before hashing it. The scoped
key lock precedes the quotation lock; order creation, snapshots, numbering, activity/audit/outbox
and the receipt commit together. Matching keyed replay returns the original live tenant-scoped
order with current permission/text projections, even after confirmation or later progress.

The one-order-per-accepted-quotation rule remains. A fresh request for an existing order succeeds
only when the normalized deposit rate and due date match its immutable creation facts. Otherwise
return ORDER_CREATION_CONFLICT without changing facts or retaining a new receipt. This explicitly
changes the unreleased V1 behavior for previously silently ignored conflicting requests, including
unkeyed ones; callers must handle409. It does not add an order-amendment operation or reprice from
mutable quotation/catalog data. Deleted/foreign order recovery fails.

The owned form retains a key for unchanged input, rotates it after edits, prevents synchronous
double submission and retains failed fields. Guidance explains that an uncertain response may
already have committed: retry unchanged or inspect the order before editing/closing/reloading.
Retry identity is local to the mounted organization/session form, not browser storage.

## Verification and rollout

Use the existing key table and constraints; no migration or dependency. Verify exact/conflicting
replay, permissions/tenants, immutable facts, rollback including numbering and concurrent requests,
plus form and browser committed-response-loss recovery. Main deployment remains separate.
Implementation and acceptance evidence belong in V1_STATUS, not an assumed release certificate.
