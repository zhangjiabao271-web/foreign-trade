# ADR-027: Explicitly limited order funding estimate

Status: Accepted by the user on2026-09-08. Implements guide2.1 without claiming actual cash needs.

The user approved: max(quoted order cost + net recorded additional expenses - net customer
receipts allocated to this order,0). Show all inputs in order currency and call the result an
estimate, never actual cash deficit, bank balance or peak funding over time. Supplier payment
dates, credit terms, unrecorded costs and actual outgoing payments are not modeled by this
formula. Zero does not certify that no liquidity is needed. No automatic financing/transfer.

Use immutable order-currency quotation cost, expense order-currency snapshots and signed
customer allocations across this order's receivables. Expense reversals and allocation reversals
subtract their original effects. Already-included expenses are not counted again. Unallocated
customer money and other orders/tenants/currencies do not fund this estimate. No live FX rate,
purchase principal or supplier payment is inferred or double-counted.

This is a separate read-only finance projection, restricted at both HTTP and service boundaries
to order.read, expense.read, receivable.read and profit.read. Under fixed roles only ADMIN,
MANAGER and FINANCE qualify. No cost-bearing result is sent to SALES/OPERATIONS/VIEWER. Existing
expense summary permissions and contracts are unchanged. Query inputs in one PostgreSQL statement
snapshot; do not combine paginated client lists or calculate money in browser floating point.

No schema migration, evidence backfill, status change, audit/outbox write or new dependency is
needed for a read. Existing business commands retain their own atomic audit trails. Add generated
API contract, protected UI, reload/error feedback and refresh after receipts/allocations/reversals
and expense changes. Verify exact decimals, net reversals, included costs, unallocated money,
multiple installments/orders, six roles, foreign tenants, no writes, browser presentation and
runtime deployment. Acceptance remains pending; user approval of the formula is not test evidence.
