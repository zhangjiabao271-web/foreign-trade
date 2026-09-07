# Companies

Activity query services apply ADR-020 Work content protection before serialization. Unreviewed
summary/details remain confidential without profit.read; stored evidence is unchanged. Human
review uses the subject-scoped Work port with original read authority and exact content/version.
Standalone entity notes and references are not released by a timeline review.

`Company` is the single commercial-party record. Roles such as customer and supplier are rows
in `company_roles`; callers must not create duplicate companies to represent multiple roles.
Every repository method and relationship carries `organization_id`.

## Archive maintenance

CompanyArchiveQuery supports tenant-filtered name/role cursor lists, details, contacts and bounded
history. Roles are batch-loaded, not queried once per company. CompanyArchiveService creates
companies with one or more roles and maintains ordinary company/contact fields with explicit
version, reason and durable command key. Contacts cannot move to another company through these
endpoints; there is no delete/merge endpoint. Existing commercial snapshots are not rewritten.

Company name normalization is shared with lead conversion. The existing organization/name
unique index arbitrates concurrent duplicates and returns COMPANY_NAME_EXISTS. New company
roles, field changes, activity, audit and outbox are atomic; outbox excludes contact PII.
Input validation is stricter than legacy read serialization, so existing website/email values
remain readable. Migration 0015 adds navigation indexes only and preserves business rows.

Backend tests cover create/edit/retry, duplicates, tenant and parent isolation, read-only member
rejection, failure rollback and previous-data migration. The /companies workspace provides list,
search, details, field/role/contact maintenance and bounded history. Browser writes use the same
authenticated proxy for POST and PUT; PUT retains origin checks and server-owned credentials.
See docs/acceptance/V1_STATUS.md for tested slice evidence and remaining whole-system gaps.
