# ADR-017: Supplier payables and recorded outgoing settlement

Status: Accepted for implementation within the approved V1 finance scope.

Finance owns payables, supplier payments and their allocations. These are separate from customer
receipts, incurred ancillary expenses and procurement retained commitments. No bank API, automatic
transfer, general ledger or tax accounting is introduced. Only ADMIN/MANAGER/FINANCE may read or
write supplier financial records via explicit payable.read/write and supplier_payment permissions.

A payable is a human-reconciled purchase-principal obligation linked to a supplier-confirmed
purchase order. The command copies its supplier/currency and requires amount, invoice/reference,
incurred date, due date, description and reason. Multiple invoices/installments are allowed, with
active principal total capped at the original purchase total. The cap is an input safeguard, not
an assertion that the original commitment is payable. Ancillary charges stay in expenses. Cancelled
or closed purchases retain previously confirmed evidence and may receive late reconciled invoices;
cancellation neither cancels debt nor fabricates refunds. Correct obligations are never silently
derived from received quantity. Commercial disagreement requires human reconciliation.

Payables have immutable original amount/currency/evidence. A versioned reason-required void
command is allowed only with zero net allocation; it preserves original evidence, void actor/date
and audit. A corrected invoice is a new payable. Supplier payments record already-occurred outgoing
payments to a supplier, with positive amount, currency, business date, method, reference and reason.
They may exist before allocation and may fund multiple payables for that same supplier/currency.
No cross-currency settlement is inferred. FX gains/losses are outside this slice.

An allocation command locks the supplier payment then sorted payables and serializes against both
available payment amount and open payable balance. Positive allocations cannot exceed either.
Repeated allocation with a new key is allowed if balances permit; unchanged retry keys replay the
same fact. Opening payment/payable versions prevent stale submissions. Reversing a payment appends
a new reverse payment and reverse allocations; original amounts/allocations remain unchanged.
Reversal records correction of erroneous outgoing evidence, not a bank refund. A payment can be
reversed only once; reversal facts cannot be allocated or reversed. These supplier-side changes
never reopen customer orders or change receipt/deposit/fulfillment completion rules.

Payable recording lock order is sales order -> purchase -> payable, consistent with procurement.
Supplier payment allocation/reversal locks payment -> sorted payables and does not acquire order
or purchase locks. Payable void locks only the payable.
Supplier recording takes a company KEY SHARE lock, compatible with foreign-key checks in
concurrent reversals; it must not hold an exclusive company lock while waiting for numbering.
All financial writes, activity, audit and ID-only outbox events commit atomically with durable
command keys. Read balances and due/overdue
states are derived from signed allocation facts using organization business time; callers cannot
submit balances or status. Bounded queries use organization filters even for primary keys.

Migration adds separate payables, supplier_payments and supplier_payment_allocations with tenant
composite FKs and reversal uniqueness. It creates no inferred historical obligations or payments.
Nonempty downgrade refuses destruction. Existing customer payment tables and semantics remain
unchanged. UI labels emphasize recorded facts, explicit confirmation, evidence and outstanding
supplier balances; these balances do not claim actual accounting profit.
