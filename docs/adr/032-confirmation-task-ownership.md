# ADR-032: Work owns the order-confirmation task

Status: Accepted implementation-boundary clarification of guide section 8.

Sales confirmation currently constructs a Work-owned Task. Delegate that insertion to Work's
noncommitting procurement-preparation port. This is part of the existing confirmation command,
not an AI-approved task and not a new task-creation API. Never fabricate an AI approval ID.

Work independently requires order.confirm. A narrow Sales-owned source port locks/reads the
active tenant order, validates its confirmed timestamp and DEPOSIT_PENDING/EXECUTING state,
and returns immutable ID/number/time/deposit-pending facts. Read under no_autoflush so Sales'
pending confirmation mutation and original task/evidence flush order are preserved. During
ordinary confirmation the caller already holds this same order lock; no inverse lock is added.
An invalid/foreign source fails before a task is staged. No generic foreign ORM writes occur.

Work stages one PROCUREMENT_PREPARATION task with the original title, HIGH priority, due time
exactly confirmation time plus two days, original details and confidential content defaults.
It does not flush, commit, add separate evidence, or return mutable ORM to Sales. The original
Sales command retains state/version/key/replay checks, evidence and transaction. Existing task
uniqueness remains the database defense; this internal port does not provide independent replay.

No schema, public API, frontend, commercial snapshot, role assignment or real external action
changes. Validate both deposit branches, direct permission/tenant/state guards, exact task
fields, no extra evidence, rollback after staging/flush and existing concurrent/replay matrix.
Source tests and deployed runtime acceptance remain distinct.
