# CRM

Activity query services apply ADR-020 Work content protection before serialization. Unreviewed
summary/details remain confidential without profit.read; stored evidence is unchanged. Human
review uses the subject-scoped Work port with original read authority and exact content/version.
Standalone entity notes and references are not released by a timeline review.

Migration 0026 preserves source text and defaults Lead notes/source and Opportunity lost_reason
to confidential. All read and command/replay responses project detached protected DTOs; business
identifiers remain visible under original read permissions. The separate CRM text-review command
requires profit.read plus domain read permission, exact version/digest, reason, confirmation and
idempotency key. It changes disclosure metadata only and atomically records activity/audit/outbox.
Later record changes invalidate release, including restoration of old text. Populated downgrade
is refused; never discard historical facts to bypass it.

Lead status changes are commands, never generic field updates. Conversion is idempotent and
atomically creates or links a customer company, contact and opportunity while preserving the
lead source. Every transition also writes activity, audit and outbox records.

ADR-031 delegates company/customer-role/contact writes to the Companies-owned conversion port
using immutable source fields and returned IDs. CRM keeps the lead lock, state/replay checks,
opportunity creation and original evidence in its own transaction; no foreign ORM writes remain
in conversion. The port independently requires lead.convert and does not commit.

Concurrent conversions of distinct same-name leads now arbitrate company creation through the
existing tenant/normalized-active-name unique index and CUSTOMER creation through the existing
tenant/company/role key. Conflict means reuse, never overwrite another company's attributes.
Each lead retains its own contact/opportunity and atomic evidence. An inactive conflicting role
fails closed with COMPANY_ROLE_INACTIVE instead of being resurrected. An unavailable company
after conflict returns COMPANY_CHANGED for explicit retry. No automatic transaction replay,
schema migration, merge API or new permission is introduced. Source tests are separate from
runtime deployment; see V1_STATUS for actual verification and remaining coverage.

## Opportunity lifecycle (ADR-014)

Tenant-scoped list/detail/history use opportunity.read; start-negotiation and mark-lost use
opportunity.write (ADMIN/MANAGER/SALES). Explicit commands require reason, current version and
durable idempotency key. WON/LOST are terminal; no generic status patch or manual win/reopen.

Inquiry and quotation commands call the CRM-owned advance_from_evidence port within their
transaction. It locks the tenant opportunity, checks originating permission/state, and atomically
writes separate opportunity activity/audit/outbox. Acceptance cannot overwrite LOST. CRM-only
commands never lock quotations, so concurrent loss/acceptance serialize without inverse locking.
Loss does not withdraw existing quotations or contact customers. Migration 0014 preserves prior
source data; legacy LOST rows require reconciliation and downgrade refuses new loss evidence.
