# Work

ADR-034: records.record_activity stages domain evidence from trusted RequestContext, while
record_system_activity retains null actors and the trusted document event correlation. Domain
callers retain authorization, subject validation, locking, replay and transaction ownership.
The recorder performs no query/flush/commit or recursive audit/outbox, and returns no ORM.
Original fields, database timestamps, evidence counts and confidential defaults are preserved.
It is not a public arbitrary-activity API and does not approve/release text or grant permissions.

ADR-032: confirmation_tasks.stage_procurement_preparation owns the original confirmation task
in the Sales caller's transaction. It independently requires order.confirm and obtains immutable
tenant-checked facts from Sales' confirmation_facts port. It stages without flush/commit or extra
evidence; title, HIGH priority, two-day due time, details and confidential defaults are unchanged.
Sales retains order/key locking, version/state checks, replay and original atomic evidence.
This is not AI task execution; no fabricated approval and no extra task.write grant are involved.

Tasks and activities are organization-scoped. Order tasks are listed only after checking
order-read permission and the organization-owned order. Completing an order task takes the
order lock before the task lock, matching order completion's lock order.

Completion is an explicit version-checked command with a required resolution note.
It atomically writes the task fact, order activity, audit and outbox. Retrying a completed
task returns the same task without duplicate records. There is no generic status patch.

Activity reads are ordered projections, not a substitute for the owning business tables.

Commercial timelines now expose cursor pages for quotation/shipment activities and sales-order
activity-history. Original domain read rights and a live tenant owner are required in both HTTP
and service paths before cursor resolution. Shared activity_page orders occurred_at/id descending
and reuses the existing owner/activity indexes; each page returns a limit+1 sentinel, not a total.
Detached content projections preserve default confidentiality and exact-version release. The
legacy order activities endpoint is retained unchanged; new UI must use activity-history to
reach records beyond100. No migration, historical backfill or additional business write occurs.
Quotation/shipment content review now uses the same owner-before-activity lock and original
domain read plus profit.read checks; releasing history never approves a business command.
Shared UI is wired for all three owners; full browser32 tests pass including order paging.
Acceptance API/Web are deployed healthy, with actual authenticated order history inspected.
Quotation/shipment-specific live history and detailed visual checks remain separate evidence.

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
