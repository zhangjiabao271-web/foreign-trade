# Inquiries

0032 adds live organization-scoped UUID cursor navigation ordered by received_at/id descending.
Status filtering remains optional; an anchor may have changed status but must remain live in the
same organization. Missing/deleted/foreign anchors return404. HTTP limit1–100 uses a limit+1
sentinel and returns page-local count, has_more and next_cursor. Two business SELECTs serve a
nonempty cursor page. Protected descriptions and identifying RFQ references retain ADR-020.
Active organization/received/id and organization/status/received/id indexes change no facts.

An inquiry belongs to one organization, opportunity and customer company. Creation is the only
V1 direct write; quotation creation advances it from `OPEN` to `QUOTING` inside the quotation
transaction. Clients never write the status field.

ADR030 moves this assignment into quotation_progress.record_quotation_created. The port checks
quotation.write and a live tenant inquiry, keeps the caller transaction and existing lock order,
and refuses CLOSED with INVALID_STATE_TRANSITION. It never accepts a requested status or commits.
Original quotation evidence remains atomic; matching quotation replay bypasses fresh progression.

The inquiry description and customer reference are source facts. Quotation versions take their
own commercial snapshots and do not mutate the inquiry.

ADR-020 / 0029 protects the original description in all query/create service DTOs without
changing the required non-null stored source. The customer reference is an identifying RFQ
number: retain visibility under original rights and forbid internal costs/profits in it.
GET/POST inquiries/{record_id}/text-review requires inquiry.read plus profit.read, exact
content/version, reason, confirmation and key; locks only the inquiry and atomically records
activity/audit/outbox. No business status is advanced. Later row changes invalidate release.
Upgrades preserve old facts as confidential; populated downgrade refuses removal of protections.

Creation supports an optional Idempotency-Key at HTTP and service boundaries. A copied,
validated request is hashed under a tenant-scoped key before the opportunity lock. Matching
replay returns the original live inquiry through its current permission-aware text projection,
even after quotation creation advances the inquiry/opportunity. It does not repeat CRM progress,
activity, audit or outbox. Changed input conflicts; deleted/foreign records cannot be recovered.
Key and all creation facts commit or roll back together. Omitted keys remain fresh registrations;
multiple different inquiries for one eligible opportunity remain allowed. No migration needed.
The owned Web form preserves the first received_at timestamp and key for unchanged input, so
an uncertain response can be recovered without creating another inquiry. Edited input starts
a new registration. Scope change/close/reload discards retry identity; inspect existing records
before registering again. See V1_STATUS for actual verification evidence and remaining gaps.
