# ADR-031: Companies-owned lead conversion port

Status: Accepted implementation-boundary clarification of guide section 8.

CRM currently constructs Companies-owned company, customer role and contact records during
lead conversion. Move this persistence behind a Companies application port; this corrects
the modular-monolith baseline without changing the business workflow or public contract.

The port requires the originating `lead.convert` permission independently, accepts immutable
source fields, and returns only company/contact IDs. It uses the caller's session and never
commits or emits separate evidence. CRM still locks and validates the lead, owns the opportunity,
records conversion references and writes the existing activity/audit/outbox in one transaction.

Preserve tenant-scoped active normalized-name conflict arbitration, CUSTOMER role uniqueness,
inactive-role refusal, source field values and contact-per-lead behavior. Existing company
attributes are not overwritten. CRM handles converted-lead replay before calling the port.
No schema, API, frontend, role assignment or external side effect changes.

Acceptance must cover direct-port permission denial, tenant separation, caller rollback,
source-field retention and the existing state, role, evidence-failure and synchronized race
matrices. Source validation and deployed-runtime validation are reported separately.
