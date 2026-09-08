# Finance

ADR-027 adds GET sales-orders/{order_id}/funding-estimate: the greater of zero and
immutable quoted cost + net additional expenses - net customer allocations to this order.
One tenant-scoped PostgreSQL statement reads all inputs in order currency with stored FX
snapshots. Reversals subtract; included expenses and unallocated receipts are excluded.
HTTP and service both require order.read, expense.read, receivable.read and profit.read.
This read does not write business facts, audit or outbox and needs no migration. It is not
actual cash deficit or peak funding: supplier timing, outgoing payments and unrecorded costs
are not modeled; zero does not certify no liquidity is needed. See acceptance ledger for checks.

ADR-020 / 0028 protects original customer Payment.notes in detached query/create/allocation/
reversal/replay responses. Receipt amount/currency, payment number and bank reference remain
visible under payment.read; references are identifiers and must not contain costs/profits.
GET/POST payments/{payment_id}/text-review requires payment.read plus profit.read, exact
version/content digest, confirmation, reason and a durable key. Review locks only the payment,
atomically records activity/audit/outbox, and never changes money, allocations or business status.
Later row updates invalidate release, even after original notes are restored. Reversal notes
are new independent confidential facts, not covered by approval of the original receipt.
Historical notes are preserved and default confidential; populated downgrade refuses removal.
See V1_STATUS for actual test/runtime acceptance; source review never releases timeline text.

V1 receivables are generated once per confirmed order as deposit and balance installments.
The backend derives their amounts from the immutable order snapshot. Currency must match
between payment and receivable; cross-currency settlement requires an explicit future FX flow.
Due/overdue use the organization's timezone; read responses derive current state from dated
receivables and signed allocation facts, never from a caller-provided balance.

Payments and allocations require a caller-generated idempotency key. Replaying the same key and
payload returns the same resource; changing its payload conflicts. Amounts are positive Decimal
values; a reversal is a new payment and new reverse allocations referencing the originals.
Original allocations remain immutable. A payment can be allocated repeatedly to the same
receivable with distinct command keys, subject to the current available and receivable balances.

Lock order is payment, sorted sales orders, sorted receivables. Order completion takes the
order lock then its receivables. No finance operation holds a receivable lock while acquiring
an order lock. Receipt recording, allocation, reversal and their activity/audit/outbox writes
commit together. Number sequences use an atomic PostgreSQL upsert.

Finance and managers may record/allocate/reverse. Only managers/admins may complete an order
or explicitly waive unsettled receivables with a reason. A waiver preserves the receivable debt.
Reversal after completion or after planning a shipment against a deposit is blocked pending
a future compensating workflow; V1 never silently invalidates delivered or completed facts.

Completion requires all quantities delivered, required shipment documents available, receivables
covering the complete order total and settled (or authorized waiver), and no open order tasks.
See ADR-008 for these implementation choices.

ADR-020 completion now returns the shared protected sales-order projection directly from the
completion application service, including already-completed replay. A custom context holding
completion/waiver rights without profit.read cannot receive cost/profit facts. Existing fixed
manager/admin completion permissions and financial invariants are unchanged; the API no longer
imports an unrestricted serializer from sales routers. Stored order costs are never redacted.

Receipt navigation accepts optional company_id, currency_code, query and UUID cursor with a
1..100 page size. Cursor anchors must belong to the same organization and active filter scope;
missing/cross-scope anchors return 404. Search matches receipt numbers/bank references literally
and case-insensitively (wildcards escaped). Ordering is received_at, created_at, id descending;
immutable ordering fields avoid tied-timestamp skips. count is page size, not total matching rows.
Allocations are batch-loaded once per page. Migration 0017 adds organization and customer/currency
ordering indexes; downgrade only removes those indexes, never payment facts. No money/state/role
semantics changed, so ADR-008 remains authoritative. Full substring search is not a search engine;
benchmark and reconsider indexing when real receipt volume warrants it.

ADR-016 adds incurred ancillary order expenses, explicitly separate from cash payments and
purchase principal. Only expense.read/write roles (ADMIN/MANAGER/FINANCE) access these facts.
Confirmed orders allow late expenses even after finalization, without changing order status.
Costs must be classified by a human as ADDITIONAL or INCLUDED_IN_QUOTATION; summary subtracts
only net additional costs from immutable quoted gross profit and labels it an adjusted forecast.
Expense currency/rate, date, description, evidence reference and reason are required. Posting and
full reversal are atomic with activity/audit/outbox and durable keys. Reversal appends a new fact;
original amount and version do not change. Lock order is order then original expense. Database
precision is refreshed before command responses so first execution and replay serialize alike.
Commands return the posted fact; GET/list derive its current reversed-by indicator. Cursor reads
are tenant/order scoped. Migration 0019 never backfills costs and refuses a nonempty downgrade.

ADR-017 supplier settlement is separate from customer receipts. Payable creation copies a
supplier-confirmed purchase's supplier/currency; human-reconciled principal cannot exceed the
original purchase total across nonvoided payables. Cancellation/closure never silently erases
debt. Zero-net-settlement void preserves the original amount/evidence and explicit void facts.
Supplier payment recording is evidence entry, not a transfer. Same-supplier/same-currency
allocations use payment and payable opening versions and lock payment then sorted payables.
Payment reversals append separate payment/allocation facts and restore derived payable balances;
they neither assert a bank refund nor reopen customer orders. Read state is server-derived.
Explicit supplier finance permissions are limited to ADMIN/MANAGER/FINANCE. Lists are bounded and
filter-scoped cursors reject mismatched anchors. Activity/audit/outbox and durable command keys
are atomic. Company KEY SHARE in payment recording avoids an exclusive-company/numbering cycle
with reversal foreign-key checks. Migration 0020 adds three tables without inferred backfill and
refuses downgrade with any supplier financial evidence. Test evidence is in V1_STATUS; frontend
and runtime acceptance must also pass before treating this as a delivered vertical slice.
