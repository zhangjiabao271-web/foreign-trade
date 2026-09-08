# ADR-033: Platform-owned domain job persistence

Status: Accepted implementation-boundary clarification of guide sections 8 and 11.

AI and Documents currently construct and mutate Platform AsyncJob records directly. Introduce
noncommitting Platform ports for their existing job creation, result binding and worker lifecycle.
Keep the existing domain transactions, job types, three-attempt limits, progress, references,
domain audit/outbox events and original flush points. Do not invoke generic create_job, which
owns another transaction and emits a different dispatch event.

Request creation independently requires ai.run or document.write, respectively. Binding an AI
run reference also requires ai.run. Domain entry points retain their full intent/target/read
checks. Ports return IDs or immutable outcomes, not mutable job ORM. Lookups explicitly filter
organization and expected job type; mismatched type/tenant must fail before mutation.

Worker lifecycle ports are internal trusted-event functions, not user commands or HTTP APIs.
AI retains run-first locking, leases, live permission checks, provider calls outside transactions,
token accounting and retry classification. Platform locks its job and records RUNNING/attempt
or the pending/terminal outcome. Permission-loss failures must remain persistable even when
the initiating user's ai.run permission has been revoked; never add that permission requirement
to this internal failure recorder. Return retry/status to AI so run/job remain atomic and aligned.

Documents retains version-first locking, validation and AVAILABLE replay. Validate/lock the
typed job before those replay/state branches, then mark success through Platform after changing
the version in the same transaction. A second lookup uses no_autoflush to avoid prematurely
flushing the pending document mutation. Preserve null-actor worker activities and correlations.

No migrations, API shapes, new roles, provider calls, storage operations, extra dispatch events
or rewritten historical data. Type mismatch rejection is an explicit internal hardening rule;
valid persisted domain jobs retain prior behavior. Test tenant/type/request-authority guards,
atomic rollback, retry/exhaustion, revoked authority, duplicate/lease handling and scan replay.
