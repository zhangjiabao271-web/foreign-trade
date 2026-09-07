# ADR-022: Bind sales-order confirmation to the reviewed version

Status: Accepted within the authorized unreleased V1 implementation scope, 2026-09-07.
Implementation/acceptance pending; this document is not test evidence.

## Decision

Sales-order confirm requires expected_version and Idempotency-Key at HTTP and application
boundaries. This explicitly breaks the unguarded unreleased V1 contract; all owned callers
must upgrade together. Main deployed containers are not implicitly upgraded. If external
consumers exist, coordinate their upgrade before deployment. No omitted-guard fallback.

Retain the tenant-scoped order lock. Under that lock a tenant/action-scoped durable command
receipt binds the order ID and request. Matching replay returns the original live order's
current protected response, even after later business progress; it never reconfirms or
creates another procurement task. Permission and deletion/tenant checks remain mandatory.
Changed payload/key reuse conflicts. A new request checks the displayed row counter before
state rules and fails VERSION_CONFLICT if stale. Already-confirmed allowed-state no-ops retain
the existing behavior only with current preconditions and record their command receipt.

Order state, timestamp, procurement task, activity, audit, outbox and receipt commit or roll
back together. Deposit arithmetic, accepted snapshots, role permissions and downstream order
completion rules do not change. Existing counters/key storage suffice; no migration/dependency.

## UI and verification

Send the displayed row counter. An explicit uncertain-result retry uses the originally submitted
body/key, not values supplied by a background refresh. New decisions on refreshed data use new
preconditions. Order/session/organization remounts discard local retry state. Nothing confidential
or authorization-bearing is persisted in browser storage by this feature.

Verify required/stale guards, same/conflicting key, current protected replay, tenant/deleted/
live authority, both deposit branches, concurrent calls, and task/activity/audit/outbox rollback.
Update generated client and old tests without weakening their business assertions. Browser
evidence must include stale-view rejection and committed-response-loss recovery in the full
order-to-refund journey. Run proportional static, regression, build and isolated runtime checks.
