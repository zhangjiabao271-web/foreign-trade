# ADR-034: Work-owned activity recorder

Status: Accepted implementation-boundary clarification of guide sections 2.3, 8 and 11.

Domain commands currently construct Work Activity directly at 38 sites. Route those insertions
through Work's noncommitting recorder, matching the existing Platform AuditRecorder/OutboxRecorder
ownership pattern. This is internal evidence recording, not a user-facing arbitrary activity API.
Domain applications remain responsible for their original authorization, subject ownership,
state rules, locking, replay and atomic activity/audit/outbox transaction.

The user-context entry derives organization, created_by, updated_by and correlation from the
trusted RequestContext. The separate system entry accepts the trusted event organization and
correlation and retains null actors. It is used by document scan completion only. Do not invent
a user, require a newly added permission, or require an AI actor to retain revoked privileges
before recording the rejection/failure evidence.

Preserve subject type/ID, event name, summary and details expressions exactly; preserve deferred
database timestamps, confidential defaults, caller flush ordering and original evidence counts.
The recorder stages one row and returns no mutable ORM; it never queries, flushes, commits,
reviews/releases contents, changes another fact, emits recursive audit/events or handles retries.
Existing historical records and Work content-review commands remain untouched.

No schema, public API, new roles, provider/storage calls or event contract changes. Acceptance
includes a structural parameter comparison for every migrated call site, no-query/no-flush
recorder probes, stored user/system origins and confidentiality, caller rollback, domain fault
matrices and full current-source regression. Source completion is not deployed acceptance.
