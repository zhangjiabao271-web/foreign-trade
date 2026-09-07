# Company archive workspace

Unified company directory, role filters and explicit name search use bounded cursor pages.
Details maintain ordinary company fields and contacts; roles are add-only, with no deletion,
merge or contact transfer. Historical commercial snapshots remain untouched.

Generated API contracts, session/organization-scoped TanStack Query caches, RHF/Zod forms,
version/reason on edits and stable unchanged-command retry keys follow the workspace baseline.
Read-only members see no write controls; errors, pending inputs and empty states are explicit.
Existing ledger colors and typography are reused. Edits retain their opening snapshot version
even if a background refresh changes the query result. Mutation forms are not remounted by
their own successful query refresh, preserving completion feedback.

Validated through form/security tests and a browser create/multi-role/edit/contact/reload/search
journey, with 375/1440 screenshots. See the V1 acceptance ledger for exact whole-suite results;
local fixture validation does not demonstrate real Logto login or production readiness.
