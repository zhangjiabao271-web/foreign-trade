# Fulfillment

Shipment activities now have an owner-authorized cursor GET at shipments/{id}/activities,
using Work's existing protected activity projection and content-review workflow. The current
milestone display is not a substitute for full activity history. No business event backfill or
state change occurs; UI integration/runtime acceptance are still in progress.

GET shipments/{shipment_id}/source-lines resolves only the current shipment's active source
lines, independent of order-list cursors. Router and query service require shipment.read plus
order.read. Sales owns the scoped parent/line lookup and existing whole-order text projection;
missing/deleted/foreign sources fail404 rather than returning a partial mapping. Output contains
only source line/order IDs, order number/status, SKU, protected description and unit, never money.
The source port accepts at most200 IDs (the existing shipment creation bound), deduplicates rows,
and evaluates disclosure against every active line of each source order. Unshipped-line changes
invalidate prior review too. Four business SELECTs serve one or combined orders without N+1.
This read-only addition writes no audit/activity/outbox and needs no migration or dependency.

Shipments are organization-owned execution plans over stable sales-order lines. A line may be
split across shipments and one shipment may combine several lines, but cumulative shipment
quantity can never exceed ordered quantity. Shipment planning requires the sales order to be
`EXECUTING` or `READY_TO_SHIP`; a pending deposit therefore blocks shipment creation.

Only explicit commands change state: book, ready, enter customs, depart, start transit, arrive and
deliver. Every command atomically writes activity, audit and outbox records. Milestone timestamps
are retained independently from the current status.

V1 requires an available `COMMERCIAL_INVOICE` and `PACKING_LIST` before `READY`, `CUSTOMS` or
`DEPARTED`. A bill of lading is deliberately not a pre-departure requirement because it is commonly
issued after departure. This is a configurable product rule to revisit before production rollout.

Order milestones are updated through the Sales-owned `refresh_shipping_progress` command port
inside the same transaction. Fulfillment does not write SalesOrder state. The public
`milestone_quantities` read port batches persisted quantities across requested organization-owned
lines. Sales rechecks quantities, locks orders in ID order and atomically records order evidence.

Creation supports optional `Idempotency-Key` at the HTTP boundary. An unchanged keyed retry
returns the original shipment's current state, stable item order and current document gaps,
without consuming capacity again or appending duplicate evidence. A changed body with the
same key conflicts. Permission checks precede replay, and resource lookup remains scoped.
Omitting the header requests a new shipment for legacy callers; this is not deduplication.
Blank or oversized supplied keys fail validation. Application-service callers supply a key.

Shipment, lines, number, activity, audit, outbox and completed key share one transaction.
Number allocation uses the shared PostgreSQL upsert helper, including concurrent first numbers
for disjoint orders. No schema change or historical-number rewrite is required.

Planning first discovers scoped source IDs without caching unlocked ORM objects, locks every
active parent order in ID order, then locks source lines in ID order and revalidates the complete
ID/parent mapping. Missing/deleted parents or lines reject atomically. Capacity and order-state
checks therefore use facts read after the parent lock wait. All seven milestones acquire scoped
parent locks in ID order before the shipment lock, aligning with procurement/order completion.
The Sales-owned progress port still owns order mutations.

ADR-025 requires ShipmentDecision.expected_version and Idempotency-Key for all seven milestones;
ShipmentBook additionally carries the reference, and response DTOs expose the existing counter.
This is an explicit unreleased-V1 breaking contract with no omitted-guard fallback. Under sorted
parent then shipment locks, action-scoped receipts bind the ID and validated request. Matching
replay returns the original live shipment's current facts/document gaps even after later progress
or parent finalization, without rerunning old prerequisites or repeating evidence/timestamps.
New requests check version, complete live source/parent mappings, executing/ready/shipped parents
and persisted cumulative quantities. Finalized/pending-deposit parents reject. Guarded no-ops
retain receipts; a different booking reference conflicts rather than replacing stored facts.
State, independent timestamps, Sales-owned order progress, evidence and key commit atomically.
Permissions and pinned AVAILABLE document requirements remain unchanged. No migration/dependency;
all callers must upgrade together before main deployment. See V1_STATUS for actual verification.

Shipment list reads batch active items and current document availability for the selected
organization/page. Nonempty pages use three business SELECTs regardless of page size; empty
pages use one. Item creation-time/ID ordering and response fields are preserved. Checklist
evaluation is shared with detail/commands: only nondeleted links/documents/current AVAILABLE
versions with immutable storage pointers qualify. Old, pending or unpinned evidence does not.
Reads create no activity/audit/outbox. No migration or permission change is required; the
prior bounded-list implementation is now extended by0032 cursor navigation.

0032 uses live organization-scoped UUID anchors and created_at/id descending order, with
limit1–100, a limit+1 sentinel and page-local count/has_more/next_cursor. Missing/deleted/foreign
anchors return404. Cursor pages add one scoped anchor SELECT to the batched list reads above.
An active org/created/id index is the only shipment migration change. This is a moving view,
not a historical snapshot; reads do not change permissions, capacity or transactional evidence.
