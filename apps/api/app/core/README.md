# Core shared primitives

Core contains configuration, database/session building blocks and explicit units of work.
Domains retain ownership of business records, access rules, commands and audit/outbox boundaries.

Content review primitives share nullable disclosure metadata, its consistency constraint and
request/snapshot wire fields. They do not authorize disclosure or mutate domain records. Each
domain must validate the original read permission, organization/owner, exact content/version,
confirmation and idempotency, and atomically preserve audit/activity/outbox evidence.
