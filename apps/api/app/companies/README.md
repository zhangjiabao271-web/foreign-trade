# Companies

0035 provisions PostgreSQL's bundled pg_trgm and partial active-company GIN indexes for
name/name_normalized literal substring search and simple full-text search. Tenant filtering
remains mandatory in every query; these nonunique indexes do not grant access or change search
ranking/matching. Company.name is nonnull, so the assistant query uses the indexed column without
redundant coalesce. Existing escaped wildcard behavior and ten-result bound remain unchanged.
Migration preserves all business rows; downgrade removes only these indexes and retains the
possibly preexisting shared extension. Local small-dataset transactional index creation takes
table locks; large production tables need an explicitly planned concurrent-index rollout.
Actual acceptance database is0035 after2026-09-08 encrypted-copy rehearsal and guarded
deployment; all45business-table fingerprints were preserved. See latest V1_STATUS.

Activity query services apply ADR-020 Work content protection before serialization. Unreviewed
summary/details remain confidential without profit.read; stored evidence is unchanged. Human
review uses the subject-scoped Work port with original read authority and exact content/version.
Standalone entity notes and references are not released by a timeline review.

`Company` is the single commercial-party record. Roles such as customer and supplier are rows
in `company_roles`; callers must not create duplicate companies to represent multiple roles.
Every repository method and relationship carries `organization_id`.

ADR-031: lead_conversion.resolve_conversion_parties owns company/customer-role/contact writes
for a caller-validated lead conversion. It checks lead.convert, accepts immutable source fields,
returns IDs and joins the caller transaction without commit or separate evidence. Its private
conversion repository retains tenant/name conflict arbitration and inactive-role refusal.
Converted-lead replay is the CRM caller's responsibility; this port is not a public create API.

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
