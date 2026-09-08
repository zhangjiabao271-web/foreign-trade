# ADR-030: Inquiry-owned quotation progression

Status: Accepted within authorized V1 implementation scope, 2026-09-09.

Guide8 requires writes through the owning module. Sales previously assigned Inquiry.status
and updated_by directly while creating a quotation. It also silently changed CLOSED to QUOTING,
contradicting the documented OPEN-to-QUOTING progression. No V1 inquiry reopening is introduced.

Inquiries now exposes record_quotation_created(session, context, inquiry_id). It checks the
originating quotation.write permission, locks a live tenant inquiry and owns the assignment.
OPEN and existing QUOTING are eligible; CLOSED returns409/INVALID_STATE_TRANSITION. This is an
explicit unreleased-V1 behavior correction for previously closed sources, not silent compatibility.

Sales retains its existing command key, inquiry-first then opportunity locking, quotation
uniqueness, pricing and CRM progress. The port rechecks the already-held inquiry lock and does
not commit, emit external calls, accept a requested status or mutate caller-supplied ORM objects.
Quotation activity/audit/outbox and inquiry change remain in the same originating transaction;
no duplicate evidence stream, history rewrite, migration or new HTTP endpoint is introduced.
Matching quotation retries take the original existing replay path before fresh progression.

Tests cover authority/tenant denial, CLOSED creation rollback, caller failure after the port's
flush and the actual Sales invocation. Broader regression and deployment must be reported
separately; this decision is not a release certificate.
