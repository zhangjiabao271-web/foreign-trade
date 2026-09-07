# ADR-016: Incurred order expenses, corrections and forecast visibility

Status: Accepted for implementation within the approved V1 finance scope.

Expenses record incurred ancillary order costs (freight, inspection, bank fees, customs and
other explained charges), not cash movements or purchase principal. Only FINANCE/MANAGER/ADMIN
can read or record them. Recording requires an existing confirmed order, positive Decimal amount,
currency, cost-to-order-currency exchange-rate snapshot, actual business date, category,
description and evidence reference. Same-currency rate must be one. No invoice or payment is
invented from procurement state. Payables and outgoing settlements remain their own financial
slice; an expense is not proof that a supplier was paid.

The operator explicitly classifies the cost as ADDITIONAL or INCLUDED_IN_QUOTATION. The latter
means it is already represented in quoted costs and must not be deducted a second time. This
classification requires human reconciliation of the evidence, not an AI inference. The order's
original quote/price/cost snapshots never change. Reports separately show original quoted gross
profit, net additional costs, net already-included costs and quoted gross profit less additional
costs. The final figure is an adjusted forecast, not actual or accounting profit.

Posted expense facts are immutable. Corrections append one full REVERSAL expense referencing
the original, copying its amount/currency/rate/classification and requiring reason and opening
version. Partial corrections are full reversal plus a corrected new expense. Reversals cannot
be reversed. Read state and net totals derive from original/reversal facts. Original amounts
are never erased. Commands require durable keys and atomic activity/audit/outbox writes.

Lock order is sales order -> original expense. Late invoices and corrections may be recorded
for completed/cancelled orders that were confirmed, with explicit reference/reason; this records
later financial evidence without reopening the order or reversing payment/fulfillment facts.
Dates are non-future in the organization's timezone. Amounts round HALF_UP to four places and
exchange rates retain eight places; overflow fails before persistence. No external transfers,
general ledger, automatic tax treatment or AI funds actions are introduced.

Migration adds only expenses with tenant/order/self-reference FKs, reversal uniqueness and
scoped navigation indexes. It does not backfill fabricated expenses and refuses destructive
downgrade once financial evidence exists.
