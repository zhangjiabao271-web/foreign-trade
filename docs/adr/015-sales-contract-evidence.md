# ADR-015: Sales contract evidence and immutable commercial snapshots

Status: Accepted for implementation within the approved V1 construction scope.

The guide names sales_contracts but delegates detailed workflow to the implementation slice.
Contracts are order-linked commercial evidence, not an electronic-signature service. A draft
copies the accepted order's customer/seller names, item selling terms, total, currency, payment,
delivery and deposit terms. It never exposes internal cost/profit in the contract snapshot.
Additional notes and an external contract reference are editable only while DRAFT, with reason,
opening version and durable command key. They do not override the commercial snapshot.

DRAFT -> SIGNED requires a human manager's explicit record-signature command, signed date,
reason and a specific AVAILABLE, storage-pinned SALES_CONTRACT document version linked to the
same order. The command records evidence of an already signed contract; it does not sign, send,
verify legal authority or change any order/price/payment state. New document versions do not
replace the version pinned by the contract. DRAFT -> VOIDED preserves evidence and allows a new
draft. Signed and voided records are immutable. Legal rescission/amendment of a signed contract
requires a separately designed compensating workflow; V1 does not silently void legal facts.

At most one non-voided contract exists per order. Cancelled/completed orders cannot acquire or
change contracts; signed records stay readable. Signing additionally requires order confirmation.
Contract writes lock order -> contract -> document version; document upload already locks its
order target before document/version. All commands atomically write activity/audit/outbox.
No new external side effects or dependencies are introduced. Reads follow order-read access;
draft writes follow sales/manager responsibilities; signature recording is manager/admin only.

Migration adds the contract table and SALES_CONTRACT document type. Nonempty contract/type
data prevent destructive downgrade. Existing orders are neither backfilled with invented
contracts nor forced through a newly inferred contract gate for order completion.
