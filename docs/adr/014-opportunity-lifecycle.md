# ADR-014: Evidence-backed opportunity lifecycle

Status: Accepted within the authorized V1 implementation scope, 2026-09-06.

The guide's opportunity states remain unchanged. Inquiry creation advances OPEN to INQUIRY;
quotation creation advances INQUIRY to QUOTING; these facts use a CRM-owned transaction port.
An explicit start-negotiation command advances QUOTING to NEGOTIATION with a reason.
Only quotation acceptance wins an opportunity (QUOTING/NEGOTIATION to WON). There is no manual
win command, generic status patch, or reopening of WON/LOST in V1.

Mark-lost accepts any nonterminal opportunity, requires a nonblank reason, current version and
durable idempotency key. It does not retract sent quotations or notify customers. Existing quote
evidence remains intact, but later acceptance cannot overwrite LOST. Concurrent loss/acceptance
serialize on the opportunity row and cannot both succeed. CRM commands never acquire quotation
locks, avoiding a reverse lock order against quotation acceptance.

Explicit commands require opportunity.write (ADMIN/MANAGER/SALES); reads use opportunity.read.
The CRM port checks the originating inquiry/quotation command permission and writes independent
opportunity activity, audit and outbox records inside the caller's transaction. No external effects.
Nullable lost timestamp/reason preserve existing rows; legacy LOST rows without evidence require
reconciliation before migration. Downgrade refuses to discard loss evidence.

Tenant-filtered list/detail/history and reason-confirmed UI provide traceability. Validation covers
terminal guards, cross-tenant routes, idempotency, concurrency, failure rollback and migration.
