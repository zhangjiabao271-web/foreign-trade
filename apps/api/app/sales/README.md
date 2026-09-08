# Sales quotations

ADR-032: order confirmation delegates procurement task staging to Work. Sales confirmation_facts
provides an immutable tenant-checked confirmed-order snapshot under order.confirm; no_autoflush
preserves the caller's pending confirmation and original evidence flush order. Work does not
commit or emit separate evidence. Sales retains commercial/state/key/replay ownership; task
fields and permissions remain unchanged. Runtime acceptance is tracked separately in V1_STATUS.

The Sales-owned settlement port independently requires payment.allocate or payment.reverse
according to the originating action, before any order mutation or evidence insertion. Finance
retains its existing entry checks, locked-order/amount validation and caller-owned transaction.
This is defense in depth under guide3, not a new role, public endpoint or financial transition.

ADR030: quotation creation delegates inquiry progression to the Inquiries-owned transaction
port rather than assigning foreign ORM fields. Existing key/inquiry/opportunity lock ordering,
quotation evidence and replay remain; a fresh quotation on CLOSED inquiry now fails atomically.
No schema/API shape change; runtime deployment and expanded acceptance are tracked in V1_STATUS.

0034 adds the missing composite `(organization_id, opportunity_id)` foreign key on sales orders.
The command still copies opportunity identity from the accepted quotation; no new request field,
state transition or business permission is added. PostgreSQL rejects missing/foreign opportunity
references independently of the application. Migration validates all retained records, including
archived orders, and fails rather than repairing/deleting an inconsistent snapshot. Downgrade
removes only this added constraint. Sep8 current-source encrypted-backup rehearsal and actual
acceptance0034 deployment preserved all45 application table fingerprints; see V1_STATUS.

Quotation activities now have an owner-authorized cursor GET at quotations/{id}/activities;
sales-order history has sales-orders/{id}/activity-history without changing the legacy limited
activities response. Both reuse Work's protected activity projection; the version ledger is not
a substitute for this full history. UI integration/runtime acceptance are still in progress.

The Sales-owned source_lines query port supports exact bounded shipment source resolution.
It requires order.read and scopes both active parent and active item by organization, failing
closed if any requested ID is unavailable. It reuses the existing full-order protected projection
so source disclosure binds all order lines, but returns only operational identifiers/status/unit
and the permitted description. No cost, profit or other monetary field enters this narrow DTO.
Existing primary/parent indexes serve two batched SELECTs; no schema or write semantics change.

0032 quotation navigation adds live organization-scoped UUID cursors, created_at/id descending
ordering, limit1–100 and page-local count/has_more/next_cursor via a limit+1 sentinel. Existing
status filters and protected current-version projections remain; a live anchor may have changed
status. Missing/deleted/foreign anchors404. Nonempty cursor pages use two business SELECTs.
The partial active organization/created/id index changes no snapshots or command permissions.

## ADR-020 commercial source text (0029)

QuotationVersion and SalesOrder terms and line descriptions, and SalesContract notes/nested
commercial descriptions/terms, now have independent content-bound disclosure review. Detached
query/command/replay projections explicitly return null text without original read plus review
release or profit authority. Selling money, SKU/unit, party names and business references remain
under existing rights. Identifiers must not contain costs/profits; this is not automated scanning.
GET/POST commercial-text/{kind}/{record_id}/review accepts only quotation_version, sales_order,
sales_contract. It requires profit.read plus the original quotation/order/contract read right,
live organization/parent, version/hash, reason/confirmation/key and atomic evidence. Quotation
review locks quotation then version; contract review locks order then contract. Finalized records
remain reviewable but never reopen; business approval/signing and disclosure are distinct.
Digest includes exact descriptions, line IDs and line versions, so restoring a changed line's
old text cannot silently restore disclosure. Contract digest includes the exact stored JSON.
Reviews never change immutable commercial values. New copies/revisions start confidential even
when the source was released. Backend copies original ORM facts; the price-only revision editor
omits descriptions rather than resending hidden nulls. Contract update preserves omitted notes
and references (explicit null still clears an authorized draft field); router preserves unset
fields and the UI omits unavailable notes. Stored facts are never redacted. 0029 adds nullable
metadata only and refuses populated downgrade. See V1_STATUS for actual acceptance boundaries.

## Frozen V1 commercial rules

- Each quotation version has one three-letter ISO 4217 quotation currency and one base-currency
  exchange-rate snapshot. Cost currency and the cost-to-quotation-currency rate are snapshotted
  per item.
- Quantity, money and exchange rates use `Decimal`; float is forbidden. Money and quantity are
  rounded to four decimal places with `ROUND_HALF_UP`, and exchange rates to eight places.
- Each line first rounds sales subtotal and converted cost. Version totals are sums of those
  rounded line facts. Gross profit is total sales minus total cost; margin is gross profit divided
  by total sales and is stored to four decimal places.
- Product text, unit, cost, price, tax, freight, allocated cost and exchange rates are copied into
  each version. Catalog changes never rewrite history.
- A sent version is immutable. `revision` copies the complete current snapshot, optionally
  replacing explicitly supplied commercial inputs, marks the old version `SUPERSEDED`, and
  creates the sole current draft.
- Sales submits a draft. A manager records approval while it remains `INTERNAL_REVIEW`; Sales can
  send only an approved review. Acceptance is idempotent, locks the quotation to one version,
  supersedes other active versions and sets the linked opportunity to `WON` in the same
  transaction.
- Every command writes the business fact, activity, audit and outbox atomically.

There is no generic status-update endpoint. Reject and expire are explicit commands.

ADR-021 is a breaking unreleased-V1 contract update: submit/approve/send/accept/reject/expire
now require QuotationStateCommand (expected_version_id and expected_version) and Idempotency-Key
at HTTP/service boundaries. There is no omitted-guard fallback. Under the quotation/current
locks, an action-scoped durable key either replays the originally affected live version or checks
both opening preconditions before any state change. Matching replay is permission-aware and
does not operate on later revisions. Changed-key input conflicts and stale new decisions roll
back the key with all business/evidence writes. Acceptance retains its opportunity lock and
validity checks; final/approved status replay does not duplicate domain evidence. The explicit
expire route precedes the generic accept/reject route so it is not shadowed by path validation.
Existing counters/key storage suffice; no migration. Update all callers before main deployment.

Quotation creation supports Idempotency-Key with a tenant-scoped durable request hash and
quotation ID. The key lock precedes inquiry/opportunity locks. A matching retry returns that
quotation's current versions through the same protected projection as reads, even after revision;
it does not reprice from the catalog or create new numbers, lines or evidence. Changed input
under the same key conflicts. Existing write permission and explicit-cost authority are checked
before replay, and a deleted or foreign quotation cannot be recovered. The key, CRM progress,
commercial snapshot, number and activity/audit/outbox commit or roll back together.
The first-party form always sends a stable unchanged-input key and blocks concurrent clicks.
Compatibility remains explicit: omitted HTTP/service keys are new commands; a second creation
for the same inquiry still returns INQUIRY_ALREADY_QUOTED rather than guessing a prior request.
Closing/reloading the editor does not persist retry identity. Existing platform storage suffices;
no migration or dependency is added. See V1_STATUS for current verification evidence.

ADR-020 quotation enforcement is being verified. Queries and resource-returning commands now
return detached permission-aware DTOs, including revision/approval/acceptance replay. Without
profit.read, version/item cost and profit fields and list profit fields are null. Selling facts
remain intact. Internal repositories still supply full snapshots for orders; no migration needed.
Create/revision reject explicit unit_cost, cost_currency, cost_exchange_rate or allocated_cost
inputs without profit.read, including nulls and keyed replay. Create validates a copied request
with unset fields preserved. Sales can create same-currency Product-based drafts or revise
source-bound lines without resending costs. Missing cross-currency rates raise
COST_PREPARATION_REQUIRED, never an assumed one. Currency changes cannot reuse inherited rates:
provide an authorized rate, or derive one only for matching currencies. Omitted source values
preserve historical costs/rates/allocations. Broader free-text/document/AI review remains open.

Quotation and sales-order numbers use the shared PostgreSQL atomic upsert allocator inside
the business transaction. Organization, document type and UTC year partition sequences;
existing Q/SO formats and historical numbers are unchanged. Concurrent first creations on
distinct aggregates cannot race on an absent sequence row. Activity, audit or outbox failures
roll back the number together with all business facts; only an uncommitted number is reused.
No migration or API/permission change is required.

Revision requests support an opening expected_version_id and Idempotency-Key. Under the
quotation/current-version lock, the command records a tenant-scoped request hash and generated
version ID in the same transaction as superseding the old version, new lines, activity, audit
and outbox. Matching replay returns that original version with its current state, even after
later revisions; changed payload/key reuse returns 409 and a stale opening version returns
VERSION_CONFLICT without partial writes. The service validates a copied request and does not
mutate caller input. Audit before-data now records the actual previous status.

Compatibility is explicit: existing callers may omit either optional guard. Missing key means
a fresh command, and missing expected_version_id means revise the locked current version;
such callers do not receive both protections. The owned Web editor always supplies both.
No schema migration is needed: existing idempotency storage and version constraints are reused.

Revision lines may include source_item_id to identify a line in the locked current version of
this same organization/quotation. Source/product mismatch is a conflict; foreign, unrelated or
older-version source IDs return 404. No position/product-only guessing is used, so duplicate
product lines and reordering remain unambiguous. Omitted items copies all current lines.
Copied lines inherit the full snapshot (including SKU/unit and omitted commercial inputs),
while explicit price/quantity/cost/description inputs override only those values. New lines
without source_item_id continue to use active Product defaults. Copying an archived product's
existing snapshot is allowed; adding it as a new line is not. Source mappings are recorded in
the same append-only audit entry. Old versions are never rewritten or backfilled by this fix.

New acceptance checks valid_until inclusively against the current organization's IANA timezone,
after quotation/version/opportunity locks are acquired and before any accepted/won mutation.
The acceptance timestamp uses that same UTC instant. The next local calendar day returns
QUOTATION_VALIDITY_ENDED (409), with no automatic EXPIRED write and no partial evidence.
An already accepted quotation is returned before this check, so later retries and downstream
order creation do not retroactively invalidate historical acceptance. Revalidation requires
a new revision and normal approval/send; no in-place extension of a sent snapshot is allowed.
No schema or API-shape change is needed. Existing error rendering displays the recovery guidance.

Guide 5.3 customer review is now reachable through mark-customer-review. It requires
quotation.send, the displayed version ID, a trimmed evidence reason and Idempotency-Key.
The quotation/current-version lock rejects stale revisions and non-SENT states; repeated
identical keys return the original version ID without additional evidence, including after
later acceptance/revision. Reusing a key with different input returns 409. Activity, audit
with reason and ID-only outbox commit atomically. No messages or customer acceptance are
performed. Existing CUSTOMER_REVIEW storage/state constraints already cover this state;
no schema migration is needed, and accepted commercial values remain untouched.

## Frozen V1 sales-order rules

ADR-023 creation accepts an optional tenant-scoped durable key; the service validates a copied
request and normalizes its deposit rate before hashing. Key lock precedes quotation lock and
the receipt commits with number, snapshots and evidence. Matching replay returns the original
live protected order even after later progress. A fresh request for an existing quotation's
order must match deposit rate/due date or receive ORDER_CREATION_CONFLICT, including unkeyed
requests. This explicitly changes unreleased V1 silent conflicting-success semantics, never
modifies stored terms, and preserves the one-order-per-quotation rule. No migration/dependency.

ADR-022 confirmation requires SalesOrderConfirm.expected_version and Idempotency-Key in HTTP
and service calls. The order lock precedes the action-scoped durable key; matching replay returns
current protected order facts, including after later progress, with no repeated task or evidence.
New decisions must match the row counter before existing state rules. Already-confirmed allowed
states still permit a guarded no-op with its own receipt. Key/state/task/activity/audit/outbox
commit or roll back together. Missing guards fail; this is an explicit unreleased-V1 breaking
contract requiring caller upgrade before deployment. No schema/amount/permission changes.

- A sales order is created idempotently from exactly one accepted quotation. It copies the
  accepted version and every quotation line into stable order snapshots; catalog and quotation
  changes cannot rewrite the order.
- V1 requires a deposit rate between zero and one. The deposit amount is calculated by the backend
  from the snapshotted order total using `ROUND_HALF_UP`; clients never submit a deposit amount.
- Manager confirmation records the confirmation fact, moves an order with a positive deposit to
  `DEPOSIT_PENDING` (otherwise `EXECUTING`), and creates one procurement-preparation task
  atomically.
- There is no generic status update endpoint. Later phases add controlled payment, shipment, and
  completion commands without weakening these invariants.
- Sales owns shipping milestone transitions through `shipping_progress.py`. The caller supplies
  line IDs and the execution milestone, never a requested order status or mutable order object.
  It re-reads Fulfillment quantity facts, batches all lines and writes activity/audit/outbox in
  the caller's transaction. Pending-deposit and finalized orders cannot be advanced by this port.

Order list reads batch all active line snapshots for the selected organization/page in one
query, preserving per-order line-number ordering and protected response fields. Order navigation
now uses an optional live organization-scoped UUID cursor with created_at/id descending order.
HTTP returns page-local count, has_more and next_cursor using a limit+1 sentinel; limit remains
1–100. Missing/foreign/deleted anchors return404 with restart guidance. First nonempty pages use
two business SELECTs; cursor pages add one scoped anchor query, regardless of page size. Empty
pages do not issue a line query. Reads create no evidence and never change commercial facts.
0031 adds the partial organization/created_at/id index for active orders; downgrade drops only
that index. No business backfill/deletion or command/permission change. Pagination is a moving
view, not a historical snapshot; newly created orders appear after an explicit restart/refetch.

ADR-020 now protects sales-order snapshots at the application-service boundary. List/detail,
create and its existing-order replay, confirm/replay and completion/replay return detached
SalesOrderResponse projections rather than ORM tuples. Without profit.read, order total cost,
gross profit/margin and item unit cost, cost currency/rate, internal allocation, line cost and
line profit are null. Sales quantities/prices/tax/freight, total and agreed deposit stay available.
Shared order_projections applies the policy without modifying stored or session-cached facts.
Internal fulfillment/finance repositories still read exact snapshots for their authorized
business rules. Router code no longer constructs an unrestricted order response. No migration
or change to command permissions, lock order, evidence or accepted-snapshot arithmetic is needed.
Quotation cost enforcement is implemented with final acceptance in progress. Procurement structured
responses and priced commands now enforce the policy; see its module README and V1_STATUS.

## Sales contracts (ADR-015)

- `sales_contracts` preserves a seller/customer and commercial order snapshot without internal
  cost/profit. Total/currency derive from the accepted order, never a caller-supplied amount.
- Sales/manager may create drafts and update external reference/notes; updates require opening
  version, reason and durable command key. Only manager/admin records a signature; it is manual
  evidence recording, not electronic signing. DRAFT -> VOIDED retains facts and permits a new draft.
- Signing requires a confirmed, non-finalized order and a non-future organization-local signature
  date, plus an AVAILABLE, checksum/size-verified and storage-pinned SALES_CONTRACT file version
  linked to that exact order. Later file replacements do not change signed evidence. SIGNED and
  VOIDED contracts are immutable; finalized orders cannot acquire/change records.
- Commands lock order -> contract -> document version and atomically write the order timeline,
  complete before/after audit and ID-only outbox. Existing order completion rules are unchanged.
- Queries use organization and parent order, stable cursor pages and scoped permissions. Migration
  0018 has composite tenant FKs, one non-voided contract/order and evidence/state constraints;
  nonempty contract evidence refuses destructive downgrade. No business data is backfilled.
