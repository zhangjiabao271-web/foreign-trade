# ADR-024: Purchase decision preconditions

Status: Accepted for authorized unreleased V1 implementation, 2026-09-07.

## Decision

Approve, send and supplier-confirm require the displayed purchase expected_version and a durable
Idempotency-Key at both HTTP and service boundaries. Missing guards fail; this explicitly breaks
the unreleased unguarded contract and requires coordinated owned-caller updates before deployment.
Approval still requires procurement.approve and profit.read; send/confirm keep procurement.write.

Acquire tenant sales-order then purchase locks, matching cancellation/amendment/source review.
An action-scoped receipt binds purchase ID and validated body, including supplier reference/date
for confirmation. Matching replay returns the original live purchase under current permissions
and disclosure, even after later progress, without duplicating timestamps/evidence. Fresh requests
check opening version and reject finalized parent orders before state changes. This closes the
legacy transition bypass around finalized orders without changing order completion rules.

Already-at-target guarded no-ops may retain a receipt; confirmation additionally requires matching
stored supplier reference and delivery date. Conflicting input never silently succeeds or rewrites
the commitment. State, timestamps, approver, activity/audit/outbox and receipt commit or roll back
together. No supplier message or bank action occurs. Quantity, pricing, receipt and cancellation
facts remain unchanged; no migration/dependency is needed.

The UI sends displayed counters. The supplier form freezes its opening version, retains failed
fields and offers explicit original-variable retry across refetches. Fresh actions require current
displayed data; session/order remounts discard local retry identity. Backend remains authoritative.

## Acceptance

Cover required/stale guards, all roles, current projection, tenant/deletion, finalized parents,
original confirmation facts, evidence rollback and concurrent key/version races. Verify owned
forms, generated contract, browser stale/lost-response recovery and isolated builds/runtime.
See V1_STATUS for actual evidence; this ADR is not a release certificate.
