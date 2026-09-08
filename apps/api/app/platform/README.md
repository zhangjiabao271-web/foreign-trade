# Platform event administration

ADR-033: domain_jobs owns AI_COPILOT and DOCUMENT_SCAN job persistence for caller-owned
transactions. Creation checks originating ai.run/document.write, returns IDs and preserves
the original flush; no independent audit/outbox or commit. AI binding requires ai.run.
Worker lifecycle functions validate tenant/type and return immutable results. They are internal
trusted-event ports, not HTTP commands, and deliberately do not require the initiating user's
current permissions so revoked-authority failure can be recorded. AI owns its lease and retry
classification; Platform applies its persisted attempt limit. Documents retains version locks
and replay, and uses the scan port with original progress/reference semantics.

Outbox remains the PostgreSQL durable delivery record. DEAD listing is tenant-scoped,
bounded and ordered by creation time/id. HTTP lists accept limit 1–100 and offset;
offset pagination matches the current Overview convention and is not a stable snapshot
under concurrent replay. Refresh/restart at page one when the queue changes.

Replay requires `outbox.replay`, a trimmed reason and a locked tenant-scoped DEAD row.
The UI supplies the displayed version; the optional API version preserves existing
callers. Concurrent replay has one winner. Reset and audit commit atomically, including
rollback when audit recording fails. Requeue does not assert consumer success.

Replay changes delivery bookkeeping, not the originating business aggregate. It reuses
the original durable event ID and consumer deduplication, rather than emitting recursive
replay events. Original business activities remain unchanged; replay has its own audit.

Responses do not expose payloads or raw broker exceptions. Only the allowlisted receipt
timeout code is retained; other errors serialize as EVENT_DELIVERY_FAILED.

## Operational monitoring (ADR-019)

`GET /api/v1/operations` requires `operations.monitor` in the router and query service;
only ADMIN receives that permission. All persisted counters filter the current organization
and nondeleted records. Reads do not create recursive audit/outbox events.

Awaiting consumer means PENDING/PROCESSING/PUBLISHED without the matching
`worker.<event_type>` receipt, not Redis length. Age starts at event creation. State counts
cover retained current records, not transition frequencies. AI known estimated cost is separate
from unknown-cost runs; approval ratio excludes pending requests and is null without decisions.
Document rejection is a validation outcome, not proof of malware detection. The scan framework
remains a placeholder until production integration is independently accepted.

API telemetry is organization-scoped and bounded to 256 LRU buckets in the current process.
Restarts/eviction reset it; histogram ranges end with an unbounded bucket. Pool diagnostics are
shared infrastructure and remain internal JSON logs, never tenant response data. Index 0022
supports organization/status/created_at queries and can be removed without deleting events.
