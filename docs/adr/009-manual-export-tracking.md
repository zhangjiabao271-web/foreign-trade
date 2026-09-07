# ADR-009: Manual export case tracking

Status: Accepted for implementation within the approved V1 construction scope.

Customs declarations belong to a shipment; each shipment has at most one V1 declaration.
Tax-refund cases belong to a declaration; each declaration has at most one V1 case.
The composite organization/parent references prevent cross-tenant case attachment.
This supports split/combined shipments without inventing an order-only legal declaration.

Customs uses explicit prepare, ready, submit, clear and reject commands:
DRAFT -> DOCUMENTS_PENDING -> READY -> SUBMITTED -> CLEARED/REJECTED.
Refund follows the guide's NOT_READY -> DOCUMENTS_PENDING -> READY -> SUBMITTED ->
PROCESSING -> REFUNDED/REJECTED sequence. Submitted facts require an external reference
and a human-supplied date, not a network call to an authority.

Each case snapshots a user-confirmed checklist of existing supported document types.
The defaults are operational evidence only, never a statutory compliance checklist.
Regional legal forms/rates remain outside the core and require a future configured adapter.
Available versions must be linked to the specific case before ready/submitted commands.
Refund readiness also requires the declaration to be cleared.

Declared value and estimated refund are explicitly human-entered facts in one currency.
Actual refunded amount is positive and cannot exceed the estimate; partial final refunds
retain the difference visibly. No tax rate, entitlement, accounting entry or government
submission is inferred. A correction to a finalized case requires a future compensation flow.

Creation uses command idempotency. Transitions require expected_version, stable errors and
atomic case/activity/audit/outbox writes. Existing case facts are never silently overwritten.
Follow-up dates may be rescheduled or cleared through an explicit versioned command with
a required reason; final/rejected cases remain immutable. The queue retains an active case
when its date is cleared, so removing a reminder never hides unfinished work.
The action Overview reads PostgreSQL in a bounded set of queries and groups actions by
business priority; it is not a static statistics display or a replacement for domain facts.
