# Work

Tasks and activities are organization-scoped. Order tasks are listed only after checking
order-read permission and the organization-owned order. Completing an order task takes the
order lock before the task lock, matching order completion's lock order.

Completion is an explicit version-checked command with a required resolution note.
It atomically writes the task fact, order activity, audit and outbox. Retrying a completed
task returns the same task without duplicate records. There is no generic status patch.

Activity reads are ordered projections, not a substitute for the owning business tables.

ADR-020 migration 0025 leaves historical/new task and activity text confidential. Order Work
query services and task completion/DONE replay return detached DTOs: unreleased title/summary
is null and arbitrary details are omitted for readers without profit.read. Status/type/time
remain visible. Stored text is never rewritten by redaction; nested JSON projections are copies.

Order-scoped review requires profit.read and order.read (also task.read for tasks), not task.write.
The reviewer inspects an exact text/details snapshot, supplies its digest/version, a decision,
reason, confirmation and durable command key. Order-before-record locking, optimistic versions,
atomic activity/audit/outbox and live-resource replay prevent stale or duplicate releases.
Release hashes bind the post-decision record version, so later changes invalidate disclosure,
even if text is subsequently restored. Review metadata does not change business task state.
Downgrade is allowed only without Work records; populated databases require a forward migration.
Non-order timeline review explicitly supports lead/company/opportunity/customs_declaration/
tax_refund_case. It requires profit.read plus the original subject read permission, validates
an active tenant-owned subject before its exact activity, and locks owner before record. Final
business states remain reviewable. Separate command scope preserves the legacy order payload.
The same review transaction, digest/version and live-resource replay apply; unsupported subjects
fail closed. CRM/company/export activity query services return protected detached DTOs before
HTTP serialization. Minimal CRM timelines do not gain arbitrary JSON fields in their API.
Standalone entity notes/references still need their own policy integration.

The explicitly supported non-order subjects also include purchase_order. Its exact activity
review requires procurement.read plus profit.read, validates a live tenant purchase and locks
purchase before activity. It neither changes purchase status nor approves original purchase text.
Procurement retains its operational metadata whitelist and always filters known structured
command-result prices from low-role output, including independently released history.

Overview exposes eight bounded, independently paginated action queues. Offset pagination is
used for the small changing operational projection; ordering is deterministic within a read,
but live state changes can shift pages, so refresh starts from the first page when reviewing
the entire queue. Counts are page sizes, not business totals. Due receivables are filtered by
net signed allocations before limiting, including partial overdue balances. Checklists batch
current available documents; no per-row queries. Each queue checks its domain read permission.
