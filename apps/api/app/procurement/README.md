# Procurement

0032 list navigation uses a live organization-scoped UUID cursor and created_at/id descending
order. Optional sales_order_id restricts both list and cursor ownership; unrelated anchors404.
HTTP limit1–100 uses a limit+1 sentinel and returns page-local count/has_more/next_cursor.
Items are batched for the selected page, eliminating per-purchase item SELECTs; a nonempty
cursor page uses three business SELECTs. Protected DTOs and command/evidence behavior remain.
Two partial active indexes cover organization navigation with/without the parent filter;
downgrade removes indexes only. Existing commercial and receipt facts are never rewritten.

ADR-024 approve/send/confirm require a displayed expected_version and Idempotency-Key at HTTP
and service boundaries. This is an explicit unreleased-V1 breaking contract with owned callers
updated together. Parent sales-order then purchase locks serialize against amendment/review and
completion. Matching action-scoped replay projects current original facts; fresh requests check
version and reject finalized parents. Guarded already-target no-ops keep a receipt, but different
supplier reference/date returns SUPPLIER_CONFIRMATION_CONFLICT, never a silent overwrite/success.
State/timestamps/approver/evidence/key remain atomic. Costs, quantity and existing permission
requirements are unchanged. No migration or supplier communication; main rollout is separate.

Purchase orders are organization-owned commitments to one supplier company. The supplier must
have the `SUPPLIER` company role. Every line maps to a stable sales-order line; cumulative active
purchase quantity cannot exceed that sales line's ordered quantity.

V1 uses one ISO 4217 currency and one cost-to-sales-order-currency exchange-rate snapshot per
purchase order. Line totals are rounded to four decimal places with `ROUND_HALF_UP`, then summed.
Supplier reference and expected delivery date are recorded when the supplier confirms.

Only explicit commands change status: create draft, approve, send, confirm, receive, close, cancel,
and amend. Each command writes
the purchase fact, activity, audit record, and outbox event in one PostgreSQL transaction.

Draft creation supports Idempotency-Key on the existing V1 POST route. First-party clients always
send one and preserve it for unchanged retries. The service requires a key and acquires the
existing organization/scope/key transaction lock before sales-order/line locks. Validated request
hash and created resource ID commit with purchase/items/number/activity/audit/outbox. Same key
with different input returns IDEMPOTENCY_CONFLICT; same key/body returns the original purchase's
current state without rechecking creation capacity or creating fresh evidence, even after approval.
Replay still requires procurement.write, profit.read and a nondeleted current-organization resource.
For V1 compatibility, omitted HTTP headers denote a fresh command and the router supplies a new
key; identical unkeyed POSTs can intentionally create separate partial purchases. This is not a
deduplication guarantee for unkeyed callers. Empty/blank/oversized supplied keys are rejected.
No migration is needed: platform idempotency_keys already supplies scoped durable persistence.

Receiving increments separate `received_quantity` facts; ordered quantity and costs never change.
Confirmed/partially received orders accept positive per-line quantities up to the remaining amount.
The purchase row lock serializes all line receipts; expected version and a durable command key
prevent concurrent/lost-response duplicate receipts. Each receipt records its reference, business
date, line increments and before/after totals in atomic activity/audit records. Activity history is
permission-checked and paginated. No inventory/WMS behavior is implied.

All lines fully received derives RECEIVED; explicit closure needs a reason and current version.
CLOSED means procurement fulfillment is complete, not supplier payment settlement. Receipt and
closure timestamps use UTC; receipt business dates are checked against the organization timezone.
Migration 0012 preserves existing commitments and initializes receipt totals to zero. Legacy
receipt states require reconciliation instead of inferred quantities. Downgrade refuses existing
receipt facts; use a forward repair. Run migrations on a verified backup copy before main deployment.

ADR-013 cancellation releases only unreceived commitments. Cancelled rows still consume received
quantity against sales-line capacity; original totals and lines remain immutable. API responses
separate original totals from retained commitment, which is not an accounts-payable balance.
Cancel/amend require procurement.approve, profit.read, version, durable command key and reason; sent or
confirmed purchases also require supplier cancellation evidence. No supplier message, return,
payment reversal or legal agreement is performed. RECEIVED/CLOSED are not cancellable.

Amendment atomically cancels the old remaining commitment and creates a linked replacement DRAFT
for the same sales order. New supplier/cost/currency/quantity snapshots undergo normal validation
and normal approval/send/confirmation. Lock order is sales order, purchase, sales lines.
Migration 0013 adds nullable evidence and a tenant-composite replacement FK/unique constraint;
downgrade refuses cancellation/replacement evidence. Original receipt facts survive the upgrade.

ADR-020: query and command services, including replay, return detached protected DTOs. Without
profit.read, currency/rate, original/converted/retained totals and item costs are null, with
quantity/date/status facts preserved. Stored snapshots are never changed by projection. Priced
creation, approval, cancellation and amendment require cost authority plus existing write/approve
permissions; FINANCE visibility alone does not grant authoring. OPERATIONS no longer holds
procurement.approve; send/confirm/receive/close retain procurement.write. Low-role activity
responses replace historical free-text summaries and expose only whitelisted operational result
metadata. 0030 now protects source line descriptions, cancellation_reason and the legacy
cancellation_reference evidence prose. Supplier confirmation numbers remain visible identifiers;
cost/profit entry is prohibited. Source GET/POST purchase-orders/{record_id}/text-review requires
procurement.read plus profit.read, exact row/line versions and digest, confirmation/reason/key,
and atomic activity/audit/outbox. Lock order is sales order then purchase, matching amendment.
Receipts and later modifications invalidate prior disclosure; replacements start confidential.
Stored descriptions and amounts are never redacted. Populated downgrade refuses evidence loss.

Purchase history now uses independent Work activity disclosure review with procurement.read
and profit.read. The historical reference accepts a receipt number or prose; it is therefore
reviewed with the exact historical summary and JSON. Source review never approves history and
history review never approves source text. Known command-result purchase amounts remain filtered
for low roles even after history release. Documents continue to use their own version review.
See V1_STATUS for actual test/runtime results; this is not universal automatic content scanning.
