# ADR-013: Cancel remaining procurement and preserve replacement history

Status: Accepted within the authorized V1 procurement implementation scope.

Guide 5.5 requires a controlled cancellation path and change records instead of editing
confirmed prices/quantities. A cancellation ends only the unreceived commitment. Original
ordered quantity, unit cost, totals, confirmation and received quantity remain unchanged.
The cancelled purchase continues to count its received quantity against the sales line;
only unreceived capacity becomes available for replacement procurement.

Cancellation requires procurement.approve, expected version, durable command key and reason.
Sent/confirmed/partially received purchases additionally require a supplier cancellation
reference supplied by the human operator. This records evidence of the operator's action;
the application does not itself notify the supplier or assert legal agreement. Fully received,
closed and cancelled orders cannot be cancelled again with a new command key. A replay of the
same successful command is safe. Received goods are not returned or deleted by cancellation.

An amendment atomically cancels the remaining old commitment and creates a replacement draft
linked by replaces_purchase_order_id. It must keep the same sales order, may change supplier,
quantity/cost/currency, and must pass normal supplier-role, sales-quantity and Decimal checks.
The replacement goes through normal approval/send/confirmation; it is never silently treated
as supplier-confirmed. Old snapshots and receipts remain accessible. An amendment of an already
cancelled/replaced record is rejected; replacement drafts can themselves be replaced later.

Lock order is sales order, purchase order, then sales lines. Creation, cancellation and amendment
share the sales-order lock, so concurrent capacity changes cannot over-procure. Every affected
purchase gets atomic activity/audit/outbox; failure rolls back cancellation and replacement.

Expose original total separately from retained commitment (received value for cancelled rows,
full value otherwise). No cancellation reverses supplier payments/payables or treats them as paid.
Supplier claims, penalties and adjustments remain separate financial facts, never erased by this
command. Inventory returns and retroactive repricing of received goods are not implied by V1.
