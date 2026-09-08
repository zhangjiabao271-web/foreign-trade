# Full-guide acceptance audit

Started 2026-09-08. This is a requirement-led audit, not a release certificate. The full
IMPLEMENTATION_GUIDE and accepted ADRs remain authoritative; section18 alone is insufficient.
Use actual current source and execution evidence. A located test is not a passing test, and
fixture authentication is not a real Logto login. Historical evidence is routed through
V1_STATUS, REAL_IDENTITY, GUIDE_18_GATES and JOINT_LOCAL_RECOVERY with their explicit limits.

Latest execution supplement: full backend1024 passed (1401.18s, exit0), covering funding and
ADR028; the29 later-added CRM/database/Overview-permission cases passed separately. Updated
full browser31 passed (3.7m, exit0), plus isolated Overview manual-refresh browser1 passed
(12.9s, exit0) with generated-contract intercepted queue rows and real application caching.
These results supersede pending references to those runs below, not the stated coverage gaps.

## Inspected requirements and concrete findings

### Guide2.2 / Phase7: action queues

Read complete work/overview.py, test_overview.py, Overview UI/tests and both module READMEs.
Eight branches select tenant-bound live lead/current quotation/order/shipment/receivable/export
facts. Due AR filters signed net allocations before pagination and links to its order; export and
shipment missing-document requirements are batched. Responses contain identifiers/actions, not
costs or source prose. Existing integration test proves paid deposit exits due/deposit queues and
enters preparation, foreign organization sees no rows and each selected queue uses at most three
statements. Current combined run18 passed (5.36s), including16 new independent permission cases
covering each queue's domain right and overview.read before any database lookup.

UI source renders server href/next_action and missing files; its test covers next page and
session partition without credentials in cache keys. Nonempty fixtures for every queue/filter,
every returned target's complete timeline and high-volume query plans require separate evidence;
some original all-queue checks are empty and cannot prove all selection rules. README says refresh
starts at first page, but current refresh only refetches current offset; reconcile that specific
documentation/behavior mismatch. No UI change made in this checkpoint.

Subsequent refresh correction: exact first-page cache invalidation plus per-queue offset reset
now implemented and tested under AppProviders' actual30s staleTime, not only a zero-stale test
default. Targeted3 and whole249 Web tests passed; latest V1_STATUS identifies deployed image and
remaining browser checks. This supersedes the refresh mismatch, not other queue coverage limits.

Subsequent nonempty selection matrix: test_overview_selection_matrix.py seeds one synthetic
chain in each disposable database and independently enumerates included states for seven queues.
All current enum values are exercised (52 queue/state combinations); each verifies inclusion or
exclusion, foreign-tenant emptiness, target href, status, next action and required-document gaps
where applicable. Soft-deleted records disappear. Quotations additionally exclude noncurrent
versions and a deleted parent. These direct test-only state seeds establish query predicates,
not legal command transitions. The eighth queue test covers future/today/overdue dates, page1/2,
partial/full receipt allocation, filtering paid rows before LIMIT, receipt reversal reopening,
and soft-delete filtering. Final combined Overview26 passed (16.38s), Ruff/format passed.
This closes the previously empty-only state selection seam, not multirow ordering for every
queue, available/replaced document completeness, business-day timezone boundaries or timelines.

Timeline follow-up: inspected quotation-workspace's version ledger and imports; it renders
version number/status/total, not an activity list. Targeted search of sales/fulfillment routers
and shipment/quotation pages/features found no activities wiring. This is a candidate guide2.2
gap requiring full route/service/UI inspection before implementation; version snapshots or
shipment milestone dates alone must not be labelled a complete business timeline.

Confirmed timeline gap from actual app.openapi(): quotation/shipment had no activities read
route; order activities accepted only limit1-100 and returned items/count with no cursor.
Quotation/Shipment command recorders persist exact owner-bound activities, while quotation UI
only renders a version ledger and shipment UI only milestones. OrderFinance requests limit100
inside an aggregated financial read and renders no older-history navigation.
Backend correction in progress: additive quotation/shipment activity cursor routes and order
activity-history preserve legacy contract and use shared protected Work projection. Extended
existing exact-content review owner checks to quotation/shipment. New tests prove105 same-time
records plus original business events traverse without duplication, six-role disclosure,
foreign/deleted owner rejection, other-owner cursor rejection, no evidence writes on reads,
reviewed-safe-row release and invalidation after edit.52 related tests passed (51.52s), with
the earlier26 commercial/Work-review run (34.63s) covering shared reviewer regression. Generated
client is updated; strict Python and Web types and ESLint pass. Frontend permission map now
matches added subject types. Full UI wiring, browser checks, query-count evidence and deployment
are still required; do not close guide2.2 from backend availability alone.

Subsequent UI/deployment evidence: shared timeline is now mounted independently on all three
details, with20-row cursor pages, session/owner/revision isolation and cached-text hiding on
pending/error. Web260 passed; query-count checks prove2 first-page/3 cursor-page/0 denied
statements. Full browser32 passed (3.3m), including complete order-history traversal, unique
records and first-page refresh. Four-overlay API/Web deployment is healthy; actual authenticated
order page renders9 stored events including creation/completion. This supersedes the above
UI/query-count/deployment pending notes. Detailed visual checks and quotation/shipment-specific
live-history assertions are not established by the order evidence. See V1_STATUS checkpoint.

### Guide4 / guide15.10,12: database evidence scope

Read complete test_migrations.py and test_legacy_migration.py. The empty-head test explicitly
compares table inventory through0033, runs Alembic metadata check, checks tenant columns and
timezone-aware *_at types, membership uniqueness/navigation indexes, outbox indexes, processed
event composite identity/FK, tenant actor FK, quotation current/accepted uniqueness and accepted
version ownership, one order per quotation, tenant purchase/shipment line FKs and document-link
index. Actual database rejects a cross-tenant job actor and audit UPDATE. The prior-identity
revision test preserves a seeded membership through head; it is not a full commercial backup
upgrade. Commercial-copy and joint recovery evidence must be evaluated separately. No assertion
here checks every money-column precision, every common field or audit DELETE; those broader
guide4/15 statements cannot be closed merely from this file's passing status.

Subsequent dedicated database tests passed2 (2.60s): inspect every PostgreSQL numeric column,
reject floating types, verify18,4 for commercial values,18,8 for FX and the existing AI micro-cost
estimate,5,2 for job progress, with explicit required commercial columns to avoid vacuous coverage.
The AI precision is recorded as an existing implementation distinction, not a new financial rule.
An actual tenant/id-targeted audit DELETE is rejected with SQLSTATE55000 and original action is
still readable afterward. These tests run only on disposable test databases. Complete common-field
and relationship/unique-index coverage still requires its own evidence; this is not a blanket pass.

Subsequent guide4 structural matrix now reflects all45 application tables from migrated PostgreSQL
(plus Alembic bookkeeping) against the explicit expected inventory. It checks UUID keys, tenant
non-nullability, actor nullability, timestamp types/defaults and integer version/default1 across
ordinary records. Global users/organizations, append-only audit and composite consumer receipts
are handled explicitly according to the existing foundation models; no new exception is inferred
from missing columns. All declared tenant-to-tenant FKs pair organization_id on both sides;
tenant unique constraints/indexes include organization_id; ordinary actor FKs target membership.
Catalog checks verify validated keys and enabled FK triggers, not just their names. An exact
13-field inventory covers polymorphic owner IDs and request/correlation/lease IDs; this does not
prove those application-side authorization paths or every partial-index predicate.

This inventory found sales_orders.opportunity_id was an unconstrained non-null UUID. A real
PostgreSQL test first demonstrated that replacing it with a foreign organization's opportunity
did not raise IntegrityError. Migration0034 and ORM now add the missing composite tenant FK.
Normal commands already copy the accepted quotation's opportunity, so no API/state/money rule
changes. Tests reject foreign/missing targets with23503 and preserve the original row;0033
populated-copy upgrade/down/re-upgrade preserves every table, while invalid legacy references
abort upgrade and keep old revision/evidence.10 focused tests passed, then81 related commercial/
AI-disclosure tests passed. Final all-table structural suite4 passed after the13-field inventory.
See V1_STATUS for encrypted current-backup rehearsal and actual0034 deployment. Common-field
storage shape is now evidenced; this does not establish every service's version-increment or
actor-update behavior, soft-delete policy, legal transition or application tenant path.

### Guide5.1 / Task006: line-by-line CRM acceptance

Read CRM/Companies README and complete CRM vertical tests and services. Existing tests exercise
NEW/QUALIFIED/CONTACTED/RESPONDED/CONVERTED, repeat conversion returning identical IDs, one
company/contact/opportunity, CUSTOMER+SUPPLIER on one company, 1/1/1 evidence per command,
invalid respond from NEW without writes, foreign list/detail/qualify/convert rejection and viewer
write denial. Source implements NO_RESPONSE/contact and NEW/disqualify but prior test search
found no direct branch assertions. Added an independent guide5.1 matrix (seven states times
five commands), three independent conversion activity/audit/outbox failure injections checking
all created objects and lead references roll back, and concurrent same-lead conversion evidence.
These additions do not change application behavior. See latest V1_STATUS for actual execution.
Different-lead concurrent same-company resolution, all six roles/commands and complete navigation
coverage are not established by the same-lead concurrency or the selected API path checks.

### Guide9.3 / guide15.11: validation errors contradict advertised contract

Sep8 source inspection of main.py and auth/errors.py confirms only ApiProblem has a custom
handler. PROBLEM_RESPONSES advertises ProblemDetails for422, but RequestValidationError still
uses FastAPI's default detail-array response. The newly built same-customer funding test first
omitted inquiry opportunity_id/description and received a real422 containing detail/type/loc/msg/
input, not code/request_id/errors. Correcting that test fixture made it pass, but does not fix
the application-wide contract discrepancy. Unknown routes likewise have no explicit HTTP error
normalization. This contradicts guide9.3; it is not waived by the passing snapshot comparison.

Subsequent ADR028 implementation now corrects request validation/framework HTTP handling and
Overview's missing error declarations; see V1_STATUS for62 related backend checks,248 Web checks
and actual API deployment. Internal programming errors are not mapped to client validation errors.

Next slice: explicitly document the pre-release error contract adjustment, normalize validation
and HTTP errors while retaining status and necessary headers, exclude raw input/context/custom
validator messages from public errors, verify malformed JSON/path/query/body/header cases and
permission boundaries, regenerate the client, and rerun affected tests. Do not echo sensitive
submitted prose or arbitrary field keys. No implementation change made in this audit checkpoint.

### Task005 inspection supplement: client types

Fresh clean drift check and both negative artifact checks passed after funding generation
(negative checks14.26s). Inspected generated-client construction and problem-details parser:
business paths use generated paths; ProblemDetails aliases the generated schema. Inventory of
feature-level named business types shows schema aliases, with local command/form/UI types.
AuthGate's local AuthSession describes a Next-owned wrapper and imports generated organization
payload; platform-health is a Next-owned aggregate, not a second FastAPI business DTO.
Raw fetch inspection located binary upload, Next proxy/session/health and test harness calls.
Some browser tests still use handwritten JSON subset assertions; exhaustive source/inline-shape
review remains before claiming the literal whole-Web no-duplicate-DTO requirement complete.

Subsequent Task005 correction: quotation lifecycle and product-supplier browser assertions now
use generated LeadDetailResponse, QuotationResponse, ProductResponse, ReceivableListResponse,
PaymentListResponse, PurchaseOrderResponse and QuotationRevisionItemInput instead of handwritten
business subsets. The two-source-item revision fixture now fails explicitly if its source list is
missing or incomplete; no empty-list fallback hides that failure. Export ManualFact derives its
fields from generated commands while retaining string-only form money and required local reason.
These are compile-time contracts, not runtime JSON validation. Web typecheck/lint,260 unit tests
and clean generated-client drift check passed. Fresh full browser execution is recorded in
V1_STATUS after completion, not inferred from those static checks.

Further inspected local shapes: IdentityEdit and SupplierEdit are editor state wrapping generated
business records; UploadRetry is a local request fingerprint, fileMetadata is constructed from a
browser File, and collectCursorItems is a generic cache-page helper. These are not duplicate API
DTOs. Raw business JSON in browser tests still includes untyped reads; replacing handwritten
subsets alone is not proof of universal runtime validation or an exhaustive test-fixture audit.

### Guide19 Task003 / guide3,10: context and tenancy

Read auth README, test_auth_unit.py, test_tenant_isolation.py and worker test_tasks.py.
The tested rejection matrix includes no token/organization, bad issuer/audience/expiry,
missing/disabled membership, disabled user/organization and mismatched token organization.
Job primary-key lookup asserts404 for the other tenant; list/count assert only the selected
tenant's job. Organization discovery tests inactive and soft-deleted identities and restricts
multi-membership by token claim. Worker tests require explicit UUID context and reject a
message/context organization mismatch before DB access. This does not substitute for the
module-by-module repository/API/tool/job matrix required by guide15.1. Current full backend
run is pending; REAL_IDENTITY separately supplies real provider/role demonstrations.

### Guide19 Task004 / guide11,15.3-4: transactions and reliable events

Read platform README and full test_platform_transactions.py. Assertions cover atomic
job/audit/outbox, injected failures at business/audit/outbox, inability to claim an uncommitted
event, two concurrent relays with12 unique publications, failed delivery becoming DEAD,
authorized and version-bound replay, replay audit rollback, tenant-limited dead listing,
duplicate consumption with exactly one mutation, intended-receipt recovery and late duplicate
after lost-message replay. RecordingDispatcher is explicitly a test double. Actual broker
restart evidence remains GUIDE_18_GATES18.9, not a claim of a new Redis failure experiment.
Current full backend run is pending. Business activity rollback must also be reconciled per
domain; the platform sample alone cannot establish every commercial transaction invariant.

### Guide19 Task005 / guide9,15.11: generated client and drift gate

Read generator script, package README and test_openapi_contract.py. Generator check makes a
temporary schema/types pair and compares both byte-for-byte against canonical files; the API
test compares the live app schema to snapshot. Sep8 `pnpm api-client:check` passed after the
download change, which changes signed URL contents but not the response DTO. CI invokes the
drift check. Sep8 added two negative probes running that actual command: test-only in-memory
stale schema/types bytes independently produce exit1 and the precise drift error/path, with
canonical disk bytes unchanged. Both passed and CI now invokes them. This is artifact mismatch
simulation, not a source-model mutation; together with direct live-schema comparison it verifies
the drift boundary. Whole-Web duplicate-DTO audit remains before closing every Task005 assertion.

### Guide0.1,17,18.10: CI and executable quality gates

Inspected .github/workflows/ci.yml, package.json, Makefile and README. Confirmed and fixed:
quality job provisioned PostgreSQL but omitted real MinIO required by document_versions test;
it also omitted the documented Playwright command. Added MinIO readiness before tests and
Chromium installation plus full Playwright execution, retaining separate container smoke.
YAML parse/order, Prettier, Compose config and client drift checks passed locally. No push or
GitHub execution has occurred; hosted CI is unverified. Local full browser31 passed in the
preceding download checkpoint; backend full rerun is still pending. Do not report remote green.

### Guide2.1: explicit advance-funding question

Search across implementation and ADRs found no labelled advance-funding/cash requirement view.
Inspected order projections and finance/expense response schemas: these expose quotation cost,
profit, installment amounts, allocated receipts and adjusted expense forecast, but no explicit
funding-needed result. Reconcile this against "需要垫付多少" before completion. These inputs alone
do not prove a dated cash requirement; do not silently label quoted cost less all receipts as
actual required cash or mix currencies/payable timing. This is an inspected acceptance seam,
not an implemented formula or an authorized change to financial facts.

Subsequent user decision: explicitly accepted the estimate max(quoted cost + net additional
expenses - net allocated customer receipts,0), with its limitations and restricted roles.
ADR027 and guide2.1 record that decision. Funding projection/API/protected UI are now implemented;
see the latest V1_STATUS checkpoint for passing targeted tests and the remaining browser/runtime
checks. The pre-funding backend baseline finished994 passed; it does not cover this new code.

## Remaining audit coverage (not silently waived)

Sep8 AI supplement (ADR029): configured user-selected DeepSeek V4 Pro with worker-only credential
and fixed official origin. Actual IAB + Logto + queued Worker + provider order summary succeeded;
five intents have individual live successes, but the subsequent combined v3 run had a parallel-call
failure. Application now denies/audits such calls and permits serial correction within four turns;
final combined live regression remains pending in V1_STATUS. Scripted68+later3 regressions pass.

Subsequent promptv4 combined real matrix passed5 in66.89s. Human samples were checked against
returned source facts, especially contractual deposit versus unknown actual payment/balance.
This supersedes that pending run only; five samples are not broad probabilistic quality proof.
This advances the earlier missing-live-provider seam, not full prompt quality, every review path,
all adversarial inputs, production scanner/hosting or the remaining requirement-led matrix.

- Guide1-2: complete product/non-goal boundary, every business question, every daily queue and
  complete timeline links. Include funding-needed seam above.
- Guide3-5: six-role permissions, common model fields/types/constraints, ownership and each
  legal/illegal state transition. Reconcile every named entity, command and accepted exception.
- Guide6-8: architectural decisions, license/locked runtime baseline, module ownership and
  specified artifacts. Merely matching directory names does not prove architecture.
- Guide9-12: request/error/pagination contracts, every tenant path, transactional/event/job
  invariants, original/current/historical file verification and authorization.
- Guide13 / ADR011,026: live provider integration/quality, private candidate review, current
  permission reevaluation, independent approval, audit and forbidden tools. Scripted tests are
  not live provider evidence; no model credentials or spend assumed from Logto setup.
- Guide14-15: all observability metrics, secret/log boundaries, complete invariant matrix,
  migration paths, benchmark scope and full recovery evidence. Production scanner and
  cross-machine disaster recovery remain explicit external boundaries, not fake local passes.
- Guide16-19: every Phase0-8 deliverable, ten end-to-end gates and Task003-006 named artifacts
  and acceptance commands, including the inspected platform/client portions above.
- Guide20-21: preserve task scope, actual validation reporting and frozen-vs-pending decisions.
- Accepted ADR008-026: full body-by-body reconciliation remains pending; do not infer closure
  from referenced ADR numbers or a historical status label.
