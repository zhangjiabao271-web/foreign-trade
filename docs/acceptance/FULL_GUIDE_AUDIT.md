# Full-guide acceptance audit

## ADR016 populated cash and expense correction boundary (Sep9)

Subsequent tenant-route check added an actual FINANCE membership in the other fixture
organization, verified authenticated context200, then exercised all five expense endpoints
(plus cursor-list variant) against the original organization's real order/expense. Every
request returned404/SALES_ORDER_NOT_FOUND rather than a permission-mask403. Complete rows in
Expense,SalesOrder,Activity,AuditLog,OutboxEvent,IdempotencyKey,DocumentSequence across both
organizations stayed identical after each request, including record with the original tenant's
key. Original-tenant replay still returned the unchanged original without writes.
Full expense-boundary file9passed/18.42s,exit0,one existinghttpx warning;
tmp/expense-tenant-20260909.xml. Initial line-width finding was formatted; final Ruff/format pass.
This closes the inspected cross-organization HTTP expense endpoint gap, not all other modules.

Read the complete ADR016, Finance README, expense model/schema/router/service, existing
expense tests and funding tests. The latter exercises net funding calculations but does not
compare complete populated cash and commercial rows across expense commands.
Added test_expense_financial_boundary.py: two classifications each exercise all five categories,
with independent JPY/CNY/order-currency conversion expectations including a HALF_UP tie.
Normal commands first create customer receipt/allocation and supplier debt/payment/allocation.
All thirteen protected tables are asserted nonempty, then their complete tenant-scoped rows
remain identical after each expense post, full reversal and replay. Original expense rows remain
unchanged; reversals copy exact amount/FX/classification/evidence fields. Summary subtracts only
additional costs and returns to original forecast after correction. Ten new facts produce ten
activity/audit/outbox records, without repeated evidence on replay.

Six HTTP role cases independently exercise list/detail/summary, record and reverse: only
ADMIN/MANAGER/FINANCE succeed; SALES/OPERATIONS/VIEWER are denied without expense/evidence count
changes. These are fixture memberships, not six new real Logto login demonstrations.
Initial targeted result:8passed/16.09s,one existing httpx warning,exit0;
tmp/expense-boundary-20260909.xml. Ruff/format pass. Combined new/original expense/funding
regression session18707 exited0:42passed/60.83s,one existing httpx warning;
tmp/expense-related-20260909.xml. This is one combined run, not fifty distinct cases.
No application code, schema,
deployment, actual money movement or business data changed. Current remote run30f931b predates
this new test-only supplement; it must not be described as remotely verified by that run.

## Deployed quotation/shipment history read supplement (Sep9)

Opened the existing synthetic shipment in the in-app browser. The initial session gate redirected
through the ordinary login link and the existing Logto SSO returned successfully without entering
credentials or changing accounts/permissions. This is not a new password/MFA test or six-role run.
The authenticated privileged view displayed SHP-2026-000001 as delivered, its original booking
reference and eight distinct descending history entries: created,booked,ready,customs,departed,
in_transit,arrived,delivered. Both history pagination controls were disabled for this one-page
sample. Explicit timeline refresh returned the same eight entries. Terminal-order guidance
continued to prohibit new shipment milestones; no mutation control was used.

Navigated through the actual quotation list to Q-2026-000001
(bdc024ff-2c12-4f66-baef-6bd68de8a61e). V2 accepted1250 and V1 superseded1200 remain distinct
from the actual seven-entry timeline: created,revised,submitted,approved,sent,
customer_review_started,accepted, in descending time order. The list has its own refresh and
disabled previous/next controls for this sample. Browser screenshots confirmed actual rendered
timeline text and controls at the current desktop viewport; no claim about all responsive sizes.
No approval,review,send,download,task completion,financial command or provider call occurred.

This closes the previously absent quotation/shipment-specific deployed read observation only.
The samples have fewer than20entries, so they do not prove multi-page live traversal; the105-row
automated service tests and separate browser pagination evidence retain their own scope.
Role-disclosure/security evidence is not inferred from this privileged read or screenshot.

## Completion/refresh command concurrency supplement (Sep9)

Read complete Finance README, completion service, refresh command, lock repository and original
finance/locking tests. Added test_completion_refresh_concurrency.py for settled and authorized
unpaid-waiver orders, using normal synthetic order/shipment/task/payment commands and a storage
double. Disposable-only stale DUE status/date and opposite UUID/number ordering make both
installments eligible. An engine-level barrier synchronizes the two actual FOR UPDATE queries;
both full application commands must finish within bounded lock waits. Complete payment and
allocation rows plus receivable IDs/amounts/currencies remain unchanged. Refresh derives PAID
or PAID/OVERDUE; completion writes exactly one activity/audit/outbox, and replay adds no evidence.

This supplements the deterministic repository-level inversion probe; it is not a production
load test, real storage scan, actual debt waiver or exhaustive interleaving proof. No business
code, schema, deployed image or real order changed. See the focused JUnit result in V1_STATUS;
the running first GitHub upload tests an earlier commit without this additional test file.

## Populated finance baseline supplement (Sep9)

New current-source finance benchmark passed1/10.27s,7operations with3warmups/30samples each.
V1_STATUS records exact data and artifacts. Six read p95 values13.093–18.486ms and receipt
create40.860ms meet guide thresholds. Nonempty results and exact financial facts are asserted.
This supersedes the absence of these selected finance read/search/create measurements only;
all-endpoint coverage,large-scale/concurrent production latency remain unproven. No app change.

## Latest deployed owner-port checkpoint (Sep9)

API/Worker/beat owner-ports images now run with matching environments,22bounded table hashes
and four unrelated container identities preserved. API live/ready200 and Redis Worker pong
passed; see V1_STATUS. A freshly loaded real SALES order page retained125CNY/37.50 deposit,
pending state and confidential text/cost redaction. No command or model request was issued.
Earlier not-deployed statements are historical; whole-guide proof is still incomplete.

## Sep9 owner-port verification checkpoint

Superseding terminal result:93777 exited0 with1292passed,5paid-skipped,1existing warning in
2084.88s. JUnit full-owner-20260909.xml confirms0failures/0errors. No source edits occurred
during the run. Earlier running percentages below are historical,not current process state.

Subsequent current-source browser40431:32passed/4.1minutes,exit0; last-run metadata agrees.
Dedicated DB,ports and process receipts were independently checked cleared. Synthetic file
bucket retained. This is fixture authentication and scripted AI,not live provider/Logto or
deployed owner-port acceptance. Broader requirement-led audit remains open.

ADR031-034 now correct the four recorded constructor/lifecycle ownership findings in source.
ADR034 targeted JUnit was independently re-read:54passed with no errors or skips. Exact API
and Worker owner-ports-20260909 image IDs plus isolated probes are recorded in V1_STATUS.
API actual uvicorn live200 passed; Worker import/eager health and six queues passed, not real
broker consumption. Existing deployment is unchanged. Full regression93777 remains live at
last observation49percent; no terminal result or full acceptance claim. Continue the broader
requirement matrix below; these owner-port checks do not substitute for it.

## Latest superseding checks (2026-09-08)

Sep9 01:19 fullregression31821 completed1253passed/5paid-skipped/1Windows temporary-root setup
error in2042.78s,exit1. The sole unexecuted process-ownership test then passed separately1/0.10s
with a verified fresh workspace basetemp. No singleall-green fullrun claim. JUnit artifacts and
remaining sourceownership work are recorded in V1_STATUS;31821 is terminal,neverpoll/restart it.

Sep9 remaining guide8 write ownership inventory is now in MODULE_OWNERSHIP.md. Full CRM
conversion source directly inserts Company/Role/Contact; order confirmation directly creates
Work procurement-preparation Task; AI/Documents directly create and update Platform AsyncJob.
Platform's generic create_job owns a separate UoW/event and cannot be used as a drop-in wrapper.
Activity constructors and worker-null-actor semantics need a nonrecursive owner-recording port.
No application/testsource changed during full regression31821; it remains live, not a final
V1 certificate. These are concrete source-bound follow-ups, not inferred security exploits.

Sep9 00:43 settlement-permission API nowdeployed:fullenv and22tablefingerprints unchanged,
sixothercontainerIDs preserved. Live/ready200 andactualruntime denies both missing originating
permissions before any order access using no-DB probes. Schema0035;preparedorderAiRuns0.
This supersedesdeploymentpending below; fullcurrentregression/realAIapproval remain separate.

Sep9 guide3/8 settlement-port audit found internal missing originating-permission recheck while
Finance HTTP/application entry checks already existed. Two denial regressions reproduced it;
Sales port now checks allocate/reverse before writes. Four direct-port plus Finance vertical
tests18passed30.34s. Candidate image builds and starts network-none withlive200; actualdeployment
remains pending. No new role/state/amount semantics or public endpoint. See V1_STATUS forscope.

Sep9 post-inquiry-port current-source browser regression:32 passed4.0m,session83527 exit0.
Isolated synthetic database migrated through0035 and was removed by teardown;3300 user session
was not operated. This supersedes pending browser regression only. Scripted AI and fixture
document processing do not establish live provider approval or production scan acceptance.

Sep9 00:21CST inquiry-owner API deployment nowverified:guardedAPI-only recreation preserved
completeenvironment,22commercial/filetablefingerprints andsixothercontainerIDs. Live/ready200,
dependencieshealthy,actualportimported,DB0035 andpreparedorderAiRuns0. This supersedespending
deployment below,not fullcurrentregression orlivebusiness/AIworkflow acceptance;seeV1_STATUS.

Sep9 inquiry ownership correction advanced: ADR030 andInquiries-owned port replacesdirectSales
mutation;CLOSEDfreshsource nowrejected explicitly. Related184tests pass247.66s;newAPIimage builds
andstarts actualuvicorn innetwork-none container withliveness200. SeeV1_STATUS forimageID and
syntax-onlyconfigurationcheck limitations. This supersedes"no runtimefix applied" as source
status only;actualacceptance deployment remainspending andrunningAPIstillusespriorimage.

Sep9 guide8 ownership audit found a concrete remaining violation:QuotationCommandService.create
in sales/services.py directly assigns inquiry.status=QUOTING andinquiry.updated_by after
locking tenant inquiry and creating quotation/version. Inquiries README assigns ownership to
Inquiries;its service currently exposes creation/query but no quotation-progression port.
This differs from the already CRM-owned opportunity advance_from_evidence call immediately
afterward. A safe correction must move inquiry mutation behind an Inquiries-owned transaction
port while preserving existing quotation transaction,lock order,error/replay semantics and
all evidence/history. No runtimefix or architectural exception has yet been applied.
Commit-location search shows OutboxAdminService explicitly commits its own repository session;
that service-level transaction alone is not evidence of a repository-internal commit violation.
Imports/assignment searches are discovery aids,not a full cross-module ownership proof.

Sep9 CRM port supplement: three evidence events x six states now independently verify
allowed/no-op/illegal branches, originating permission removal, foreign-ID rejection,
whole-row/evidence preservation and caller rollback after a successful flushed port return.
Final3 tests pass6.77s after fixing a test-helper loop binding; combined15 passed beforehand.
Synthetic evidence IDs are not proof of caller source existence validation or all failures.

Sep9 ADR014 explicitcommand matrix:all6roles x6states x2commands(72HTTPcombinations) now
checksindependentallowsets,whole-row/evidence/key preservation ondenial,stableillegalstatecode,
actor/version/1-1-1evidence onsuccess andidempotentreplay. Original lifecycle plusnewmatrix
21passed36.26s. This supersedesmissingexplicitOpportunityrole/state coverage,not evidence-port
transitions/permissions,allreads orrealidentityacceptance. No productioncodechange.

Sep9 supplement: shared documentchecklist metadata matrix now coversall4linktypes/all5states,
invalidimmutablepointers,exacttenant/type/target boundaries,threeownerrowsoftdelete exclusions,
pendingreplacement ignoringretainedavailablehistory,andavailablev2 preservingoriginalv1.
Fourmatrixcases plusOverview scaling pass5/15.04s;successfulprojectionrunsREADONLY,oneSELECT
fornonemptyrequirements/zeroforempty. This strengthens available/replaced-file selection
evidence,not realobject/scanner acceptance,homepageUIflow orconcurrentreplacement guarantees.

Post-type-correction fullWeb262tests/45files passed23.60s;wholeWebTypeScript andESLint exit0.
Independent actualOpenAPI/clientgenerator --check passes. These current checks supersede
targeted-only validation ofcompany/shipment type edits,not browser/backend/liveAI evidence.

Task005 follow-up removes shipment upload's string-to-DocumentType assertion byrequiring the
generatedtype at the mutation boundary. Existing Zodvalidated create andgenerated replacement
sources pass wholeWeb TypeScript;Shipment35tests andtargetedlint/format pass. This is compile-time
boundary repair,not new runtime validation orproof ofallWeb casts/DTOs.

Task005 deeper AST inventory found one concrete request mirror:companies add-role body's
handwritten{role:CompanyRole} duplicates generatedCompanyRoleRequest. It now directly references
the generatedschema. WholeWeb types,targetedESLint/Prettier and6companyformtests pass;type-only
change requires noAPI/runtime deployment. The106file/277literal inventory includes frontend
state andnestedtypes;it is not proof that allremainingaliases/casts/dataflow have been reviewed.

Task005 current contract check: actual generator --check completed successfully andboth
stale-schema/stale-TypeScript negative tests passed2/10.011s (session76294 exit0).
Source inspection distinguishes generated business DTO aliases from frontend-owned state:
AuthSession wraps generated MyOrganizationsResponse under the Nextsession route;PlatformHealth
validates the Nextplatform-health projection,not a duplicate FastAPI business response.
UploadRetry andSupplierEdit/IdentityEdit represent retry/dialog state andretain generated
business objects. ProblemDetails aliases the generated schema;AI andsupplier mutation bodies
use generated schemas andreturn typed client data. Declaration searches across app/components/
features/lib/shared-types locate remaining review scope;search matches andthis selected-source
inspection do not yet prove whole-Web absence ofinline mirrors orunsafe type assertions.
No application changes ornew architecture exception introduced;hostedCI remains unexecuted.

Guide18 all-eight-queue nonempty query scaling supplement now passes: new
test_overview_query_scaling.py plus original overview/state-selection files11passed27.85s.
Each queue has21rows (receivables42); fresh READ ONLY sessions retrieve limits1/20/100.
Business SELECTs stay2for leads,quotations,deposits,preparation,receivables and3for
shipment/customs/refund checklists. Checks require nonempty exact counts,identical page
prefixes,unique IDs,remaining-page traversal,missing-file projections andforeign emptiness.
This supersedes empty-only query-scaling evidence,not large-data latency,concurrent pagination,
available/replaced-file completeness or legal transitions of synthetic prepared states.
Initial new-test failure was missing explicit receivable generation in setup; corrected
through normal generate command (two rows per order),not changed production predicates.

Guide18 performance scope revalidated at23:43CST: four existing benchmark-bearing test
files passed7/103.92s,exit0. Current artifacts cover3basic reads,lead creation,AI job
acceptance,4commercial cursor lists,order cursor list andsingle-shipment source lookup.
All measured thresholds pass;GUIDE_18_GATES now records the current timestamps/samples
instead of the superseded Sep6 values. Inspected real test setup uses disposable PostgreSQL,
local token verification and no worker/provider execution. This is single-concurrency ASGI,
not network/Logto/browser/production latency. Complete ordinary endpoint/command coverage,
all8populated Overview query-scaling paths and broad financial/detail/search benchmarks
remain missing. Do not treat the successful selected11operations as guide-wide closure.

Guide11.3 reservation gap now corrected:actual Celery registry contains all6specified names,
durable/direct bindings verified; existing3event classes retain default task publication.
34related tests pass;isolated Redis6synthetic round-trips and actual Workerdefault consumption
pass. Acceptance Worker/beat updated and checked;seeV1_STATUS for initial probe/deployment
failures and successful correction. This supersedes the queue-gap findings below,not dedicated
queue consumers,new external actions or a new broker-loss recovery demonstration.

Further ADR019 matrix: current monitor7passed7.25s also covers all5job/all4AI/all3approval
states with different2tenant multiplicities,exact8decimal known costs,tokens and unknowns.
Pending approval exclusion from ratio verified. Together with preceding document/receipt
tests this supersedes missing nonempty monitored-state aggregation evidence,not business
state transitions or production observability. No runtime change was needed.

Guide11.3 candidate implementation gap confirmed from full Worker app/dispatcher/README:
only default queue is configured,explicit send and container consumption use default,and
no six-name task_queues reservation exists. ADR011 does not waive reserved queue names.
Next slice should add and verify actual Celery queue registry entries while preserving
default publication/consumption unless a separately tested routing change is necessary.

Current0035runtime full backend/Worker1218passed,5paid-opt-in skips;Web262unit and32browser
passed. Search indexes/sharedshadcn-derivedButton deployed with45table preservation and actual
manager-session refresh. SeeV1_STATUS for exact images and scope; this is not total closure.

ADR019 supplement: four new monitor tests (file6passed7.66s) exercise all5document states
with nonempty2tenant fixtures and deleted-version exclusion,retained historical versions,
softdeletedAI/job/approval accounting,intended-vs-unrelatedconsumer receipt,dead/deleted queue
exclusion and nonnegative clock-skew age. Successful service reads execute inside real
PostgreSQL READ ONLY transactions;permission denial issues0SQL. This closes those specific
previously noted evidence gaps,not every nonemptyjob/AIstate or everylog/UI/production sink.

Started 2026-09-08. This is a requirement-led audit, not a release certificate. The full
IMPLEMENTATION_GUIDE and accepted ADRs remain authoritative; section18 alone is insufficient.
Use actual current source and execution evidence. A located test is not a passing test, and
fixture authentication is not a real Logto login. Historical evidence is routed through
V1_STATUS, REAL_IDENTITY, GUIDE_18_GATES and JOINT_LOCAL_RECOVERY with their explicit limits.

Latest Sep8 superseding execution checkpoint: current-runtime backend/Worker19297 completed
1133 passed,5 paid-live-opt-in skips,1 deprecation warning in1514.13s, exit0. Later test-only
legacy11/procurement-finance4/contract-draft6/last-admin8 passed separately, not in that1133.
Corrected browser91042 completed32 passed4.0m. These supersede historical pending-run statements,
not their unproved requirements, real sales TASK_DRAFT or independent execution approval.

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

Subsequent deterministic different-lead test synchronized both missing-company reads and failed
with a PostgreSQL unique violation. Conversion now uses conflict-safe inserts targeting exactly
the existing company/role business keys, followed by organization-scoped reads; it does not update
the winning company's data. Separate barriers cover missing-company and existing-company/missing-
role races. Counts prove one shared company/role and two distinct contacts/opportunities with two
sets of evidence. An archived-role regression verifies conflict without partial conversion or
reactivation. See V1_STATUS for final passing commands and deployment status; this does not close
every concurrent archive edit, all-role path, or unrelated tenant/state invariant.

Subsequent Lead-only role/state completion: six HTTP fixture memberships times all seven Lead
commands, direct-service permission denials, all six foreign-ID command rejections, and all seven
conversion states now asserted. Allowed persisted status/actor/version and evidence counts,
denied unchanged rows and legitimate converted replay IDs are checked. Final CRM matrix28 passed
25.82s, including original35 transition-pair assertions. This supersedes the missing Lead command
role/conversion-state seam, not Companies/Opportunity roles, every read/search/archive path, real
six-identity login, UI navigation, or every concurrent company archive race.

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

### Guide6-8 technical and license baseline inspection

Subsequent pg_trgm implementation:0035 adds bundled extension plus active partial GIN indexes
for name/name_normalized substring and simple full-text search. Removes redundant coalesce on
nonnull company name; no search semantics/tenant boundary changes. Targeted83564 completed18
passed34.60s (search, archives, migration and prior opportunity-FK regressions). Tests compare
all tables in a populated0034 copy through repeated upgrades/downgrades, retain shared extension,
and check literal wildcard escaping, noncontiguous fulltext, soft deletion, tenants/permissions
and ten-result bound. Empty migration and metadata checks pass. No deployed database changed.

Actual captured queries choose all three intended indexes on6001 rows after normal VACUUM ANALYZE.
Earlier plan test failed because fresh bulk GIN pending lists made sequential scans cheaper;
ANALYZE alone did not resolve that. No planner-force setting was used. This proves selective
query plans at the stated maintenance state, not universal index use or guide-wide p95 targets.
Ruff/format, strict mypy212 and generated-client drift passed; Compose config quiet exited0 with
host Docker-config access warnings, not a container build/start check. New real backup rehearsal,
deployment and whole-runtime regression remain separate. Follow live76612 for AI/CRM regressions.

Read root/manifests, all three Dockerfiles, architecture/database/infrastructure READMEs and CI.
Compared ten installed Python primary-package versions with uv.lock; all match. Read22 Web
direct/development installed package metadata and declared versions/licenses. Recorded actual
values, source limits, stable-line container tags and outstanding obligations in
docs/architecture/BASELINE_AUDIT.md. This is not a complete transitive SBOM or legal certificate.

Concrete guide differences found: CompanyAssistantQueries uses escaped substring plus PostgreSQL
simple full-text query, but current app/migrations have no located pg_trgm extension/index/query.
Web/packages UI source/manifests contain no located shadcn/Radix integration despite guide7.
Both require implementation/reconciliation, not silent waiver or cosmetic unused dependency
installation. Cross-module write ownership and duplicate DTO audits remain separate. No package,
runtime image, schema, deployment or business fact was changed by this read-only inspection.

### ADR027-029 funding, errors and provider reconciliation

Read all three ADR bodies, complete funding repository/query/router and funding tests, request
error handlers/registration/tests, provider adapter/protocol tests and opt-in live-test body.
Funding uses one correlated PostgreSQL statement for exact order-currency cost, signed additional
expenses and signed allocations; no browser arithmetic or supplier principal/payment inputs.
Existing tests verify unallocated money exclusion, two installments, expense/receipt reversals,
included-cost exclusion, zero floor, stored FX rounding, same-customer other-order isolation,
six-role HTTP/service access, four independent permission denials before SQL and deleted/foreign
order rejection. No-write evidence is financial/evidence counts plus SELECT-only capture, not
full snapshots of every persisted table. This does not establish all mixed-currency corrupted
legacy facts or concurrent reversal snapshots, despite the one-statement implementation.

Funding UI is session/order scoped, hides cached amounts after refresh error and provides explicit
limitations/retry. A refresh in flight still displays prior data with an updating indicator;
initial pending has no invented zero. Tests cover low-role no-query, delayed/error recovery, session switch and
refresh-error confidentiality. Browser source asserts limitations, expense post/reversal and
allocated deposit refresh; latest completed32 browser baseline remains the execution evidence.

ADR028 handlers expose fixed validation location/category entries capped100 and whitelist only
Allow/WWW-Authenticate/Retry-After. Unknown framework details are replaced by HTTP phrases;
ApiProblem handling remains separate. Existing tests exercise malformed JSON, authenticated
path/query/body validation, secret-bearing custom errors, cap100,404/405, protocol headers and
all advertised422 schemas. They do not prove every arbitrary business-created ApiProblem detail
safe or normalize programming errors into422; neither is claimed by this checkpoint.

ADR029 adapter pins official destinations, disables redirect/preload and bounds reads to1000001
bytes. Existing tests prove provider credential isolation, namespace mismatch rejection before
network, absent-key no fallback and strict request options. New test_ai_provider_failures.py adds
20 cases across both providers: redirect/401/429/503, oversize, invalid JSON, invalid/missing usage,
read exception and incomplete result. Each checks exactly one selected destination request,
bounded or absent body reads, safe error code and close/release. HTTP transport is explicitly
mocked; no paid call or universal network-failure guarantee. Combined provider/error39 passed
6.34s, exit0, including20 new tests. Ruff/check/format passed; code-simplifier review kept the
scenario table and explicit cleanup assertions without changing production code.

Real five-intent promptv4 success and prior identity/worker journeys remain separately recorded;
the live test only checks required tools, positive token counts, selected privacy and unchanged
order status, with human quality inspection recorded elsewhere. It does not prove arbitrary
future model accuracy, every business column unchanged or pending real task execution approval.
No source runtime/schema/deployment/secret/business data changed in this checkpoint.

### ADR026 content review and execution authority supplement

Read ADR026, AI README, full disclosure service/projections, ApprovalService, Work approved-task
port and full disclosure tests plus existing execution tests. Disclosure release binds current
run/candidate digests; a new pending candidate removes old creator visibility. Execution requests
use the released candidate title for low-privilege owners, and execution approval uses its own
stored proposal and human decision. Revocation does not silently rewrite an existing execution
proposal; disclosure and execution remain independent. Real TASK_DRAFT user journey remains open.

Added test_ai_disclosure_atomicity.py: revise/release/restrict x three after-insert evidence
failures. Uses an explicit safe candidate, with prior release before revise/restrict. Complete
run/tool/candidate/approval/task/order/line/evidence/key snapshots survive failure unchanged,
including creator visibility. Same-key retry produces the intended change once; revisions retain
all prior rows and become pending; replays add no writes. No task, execution approval, original
run or commercial fact changes. Final73485 exit0:9 passed15.96s with scripted provider only.

Added test_ai_execution_roles.py: six fixture roles x approve/reject, independently expecting
only ADMIN/MANAGER to decide. All other roles, including FINANCE, fail403 at HTTP and direct
service boundaries with complete snapshots unchanged. Authorized approval makes one correctly
owned follow-up task and two evidence entries per kind; rejection makes no task and one decision
entry per kind. Original run/candidate/order facts stay unchanged; service replay adds nothing.
Final70135 exit0:12 passed19.95s. Initial formatting check required only line wrapping, now fixed;
Ruff/check/format and diff whitespace pass. Code-simplifier review kept explicit policy roles and
complete snapshots, reusing the new snapshot helper rather than duplicating it.

These21 tests supplement, and are not included in, the1133 full baseline. No application source,
schema, deployment, real identity, paid-provider request or real business record changed. This
does not prove all membership-change timing races, every malformed candidate, all scope/owner
combinations or the pending real sales/manager TASK_DRAFT execution journey.

### ADR024/025 decision-test audit and cross-order rollback supplement

Read complete purchase/shipment decision test bodies. Purchase tests cover three actions,
six-role HTTP/service replay, required/stale/conflicting/no-op guards, original supplier
reference/date conflicts, finalized parents, parent-finalization lock waits, current privacy,
foreign/deleted replay, nine evidence faults and nine concurrent key/version cases. Shipment
tests cover seven actions, six-role replay, later legal progress preserving timestamps/current
document gaps, finalized/pending/deleted/overcapacity sources,21 evidence faults and21 concurrent
cases. These belong to the completed1133 baseline. Neither test file alone proves every illegal
state combination or every mixed-parent/permission/archived-source transaction.

Read Fulfillment README, shipment milestone transition and Sales-owned shipping_progress port.
Existing shipment fault tests compare status/version/timestamps and evidence counts but do not
directly prove full parent-row rollback when failure occurs in the order-side evidence insert.
Added test_shipment_parent_atomicity.py: ready/depart x one/two combined source orders x three
parent activity/audit/outbox after-insert failures. Orders and shipments are prepared using normal
commands; only faults are injected. The selected last UUID parent is observed after its SQL
evidence insert and raises before commit. Complete snapshots of orders/order lines, shipments/
shipment lines and all activity/audit/outbox/idempotency rows equal their pre-command values.
Unchanged retry progresses every parent once, preserves all non-progress order fields and line
snapshots, and appends exactly parent_count+1 evidence rows per kind. Replay adds no writes.

Initial fixture attempts failed before the two-parent scenario because the shared setup creates
fixed product SKUs, then because the new inquiry omitted required description. Reused catalog
inputs with distinct normal inquiries/orders and supplied the required field; no product code
was changed or business assertions weakened. Final22061 exit0:12 passed25.47s. Ruff/check/format
and diff whitespace passed. Code-simplifier review retained explicit domain steps and complete
snapshots; last-parent ID is computed once. Disposable PostgreSQL and explicit fake object
storage only, not a new real MinIO/browser/Logto run. No migration/runtime/deployment change.

### ADR022/023 order request reconciliation

Read both ADRs, Sales README, complete order_services.py and both confirmation/creation
idempotency test bodies, plus browser creation/confirmation recovery sections. Creation hashes
a copied normalized request, locks key before quotation and checks immutable deposit terms on
fresh existing-order requests. Confirmation locks order before its action key, checks fresh
version before state rules and commits its preparation task with evidence. Both replay through
current protected projections rather than cached privileged responses.

Confirmation tests cover zero/positive deposit branches, malformed guards/keys, unchanged and
conflicting retry, guarded no-op, all six fixture roles at HTTP/service replay boundaries,
stale draft, current reduced-permission projection after later progress, foreign/deleted order,
four task/evidence fault points and three concurrent request modes. Creation tests cover
normalized same-input replay after confirmation, changed deposit rate/date for existing/fresh/
omitted keys, all six fixture roles, tenant/deletion, independent text release/restriction,
four snapshot/evidence failures including new numbering-row rollback and four concurrency modes.
These do not exhaust all deposit precision/date validation values, all downstream final states,
every complete-row rollback field or failure of an already-existing numbering-row increment.

Browser creation fetches the committed201 before dropping the response, retains fields and
retries identical body/key to the same order ID. Confirmation separately proves stale-view409
and identical-body/key recovery after a committed200. Fixture token switches in these isolated
tests are not real Logto user authentication; actual manager creation/confirmation of the new
SO-2026-000002 is separately recorded. No live order or identity changed in this source audit.

### ADR021 quotation decision reconciliation

Sep9 subsequent matrix evidence supersedes the specific role/state gaps described below:
test_quotation_decision_roles.py36passed; test_quotation_decision_states.py49passed; separate
customer-review/revision six-role/eight-state matrix96passed. New denials compare complete
quotation/version/item/opportunity snapshots plus evidence/key counts. Three existing related
files reran20passed. V1_STATUS names individual JUnit files and exact fixture boundaries;
state seeds isolate guards and do not prove natural reachability of current SUPERSEDED.
This does not expand the older fault-injection assertions or browser recovery scope below.

Read ADR021, Sales README, six decision methods and their shared transition/receipt helper,
the complete test_quotation_state_commands.py and browser stale/committed-response-loss section.
The helper binds quotation ID, action and both version guards under caller-owned parent/current
locks. Replay reads the original tenant/quotation-bound nondeleted version and applies current
projection; fresh calls compare both guards. Accept retains opportunity locking and local-date
validity checks. Business approval and text disclosure remain distinct.

The dedicated test body enumerates six actions: missing/invalid guards and keys, successful and
conflicting replay, selected denied/foreign contexts, protected current-permission replay,
stale revision and row counter, original-version replay after revision, deleted parent denial,
18 activity/audit/outbox failures and12 same/different-key concurrent cases. Rollback assertions
cover state/version/approved timestamp and evidence/key counts, not complete snapshots of every
commercial and linked opportunity column. Selected contexts are not the complete six-role HTTP
matrix or all legal/illegal quotation state combinations. Those broader requirements remain open.

Browser evidence uses a separate authorized disclosure change to make the displayed counter
stale, verifies VERSION_CONFLICT, then fetches a successful submit response before deliberately
aborting delivery. Explicit retry sends identical body/key and reaches internal review. This
proves the submit recovery path, not browser loss recovery for every one of the six actions.
The corrected32-test browser run is recorded in V1_STATUS; current backend19297 is still running
at this checkpoint. No application code, real commercial fact or account was changed here.

### ADR019 operational observability reconciliation

Read full ADR019/Platform README, API formatter/metrics, Worker lifecycle observers, safe-log
tests, OperationsQuery and monitor integration tests, Web tests and browser journey. Formatter
does not format library messages/arguments/exceptions; application observations use declared
fields. Tests inject header/query/path/exception secrets, check correlation, detached bounded
LRU buckets,1000 concurrent samples and telemetry failure retaining HTTP201. Worker tests
exclude arguments/results/unknown task names and invalid tracking IDs. These tests verify their
specific sinks, not universal third-party process output or arbitrary application-created fields.

Persisted queries filter organization/deletion and match the intended consumer receipt; AI
known cost is separate from unknown-run count, approval rate uses only decided requests and is
null without decisions. Existing two-organization fixtures verify exact counts/tokens/cost/rate,
no-session samples and admin-only access. Web tests cover explicit unknowns and no unauthorized
request; browser journey covers admin refresh/window limits and375/1440 overflow assertions.
Those sources do not prove every nonempty document-state counter, read-side no-write assertion,
all pending/error UI transitions or every production log sink. Current full execution is still
tracked separately; prior successful baseline does not replace those missing scope checks.

Read-only current-container sample: API150 and Worker150 recent nonblank lines parsed as JSON;
both had zero non-JSON lines and zero unexpected field names. Raw log values were not returned
to the transcript. This is a bounded current format check, not exhaustive secret-value scanning,
historical retention or production observability acceptance. No logs or runtime data changed.

### ADR016/018 expense and organization-administration reconciliation

Read full ADR016, Finance README, expense service/repository/schema and existing expense tests.
Posting requires confirmed order, nonfuture local date, positive fixed-scale money/rate,
same-currency rate1 and converted overflow guard. Included costs are reported separately, not
subtracted twice. Reversal copies original FX/classification/amount into a new fact under order
then expense locks; net summaries apply signed effects. Existing tests cover rounding/overflow,
selected permissions/tenant/cursor/version guards, late finalized-order expense, duplicate and
reverse-of-reversal denial, one concurrent reversal and all six post/reverse evidence failures.
No payment or order snapshot mutation occurs in the source. Every category/role, all local-day
boundaries and populated multi-currency/cash-preservation combinations are not proved by that
single primary journey; this checkpoint adds no expense runtime code or fabricated money facts.

Read full ADR018/Identity README, administration service/repository and tests. All writes lock
organization before reauthorizing an active nondeleted ADMIN against current membership and
global user, then acquire durable keys. Last-admin count uses matching active/nondeleted rules.
Existing tests cover stale admin, concurrent mutual demotions, five operations x three evidence
failures, foreign IDs/cursors/commands, preserved global names, inactive identities, setting
versions/timezones, membership lifecycle and index migration preservation. No remote user or
password API is called. Local fixture identity is distinct from real Logto acceptance.

Added test_last_admin_eligibility.py: second ADMIN membership disabled/deleted or its global user
disabled/deleted must not permit last-valid-admin disable/demotion. Eight scenarios passed12.83s,
with unchanged complete target row and user/member/evidence/key counts. This tests the explicit
eligibility definition, not every cross-organization identity race or all stale-context actions.
No real identities, application source, schema or deployment changed.

### ADR014/015 lifecycle and contract body reconciliation

Read both ADR bodies, full opportunity service/lifecycle tests, contract service and document
evidence port, Sales README and full contract tests. CRM's evidence port checks the originating
permission, tenant and source state under the opportunity lock and never commits independently.
Explicit loss/negotiation use version/key/reason and do not acquire quotation locks. Existing
tests prove loss blocks later acceptance without quotation/evidence mutation, one winner for
loss-vs-acceptance, protected separate history, selected tenant/cursor permissions, loss rollback
and loss-evidence migration preservation. Those tests do not enumerate every state/role/port
failure path; this is not blanket CRM closure.

Contract service locks order then contract, copies only declared selling snapshot fields,
checks confirmed/nonfinalized order and local nonfuture date, and requires document.read plus
exact same-order AVAILABLE/pinned/checksum/size evidence. File pointer is independent of latest
document version. Existing tests prove immutable snapshot after party rename, historical pointer
after replacement, signed update/void denial, one nonvoided contract under concurrent creation,
draft void/recreation, selected tenant/version/evidence guards, creation/signature evidence
rollback and destructive-downgrade refusal. There is no external signing or banking call.

Added test_contract_draft_atomicity.py for update/void x activity/audit/outbox insert failure.
It compares complete contract rows and evidence/key counts after failure, retries the same key,
checks version and exact updated notes/reference, preserved commercial JSON and no repeated
writes on replay. Test-only fixture PostgreSQL; no application code or real contract changed.
See V1_STATUS for final targeted run. This closes the inspected draft-command rollback seam,
not every role/state, all monetary snapshot fields, document-row concurrency or legal validity.

### ADR013/017 cross-module procurement and supplier-finance evidence

Read ADR013/017 and Procurement/Finance READMEs, complete purchase-change tests, cancellation,
amendment, draft-creation/capacity implementation and the supplier-settlement fixture/primary
financial journey. Cancellation preserves ordered/received lines and original costs; amendment
uses the same sales parent and normal supplier/quantity/Decimal validation, creating DRAFT.
Both share the sales-parent lock with capacity creation. Existing tests prove retained quantity,
excess-capacity rejection, linked draft/replay, invalid replacement rollback, foreign rejection,
receipt-vs-cancel version race and selected activity/audit/outbox failures. They did not directly
exercise a purchase change while recorded supplier debt/payment/allocation already exists.

Added test_purchase_finance_boundary.py with four scenarios: cancel/amend x unreceived/partly
received. The normal API chain records100 CNY original procurement,60 obligation,40 outgoing
payment and25 allocation before changing procurement. Complete financial-row snapshots and
sales-order/receivable rows remain identical; original procurement lines/prices/confirmation
remain, with replacement unapproved. Read projection still shows35 payable balance and the
payment retains15 available. Unchanged-key replay also preserves financial facts. A late40
invoice on the cancelled original is accepted; an additional0.0001 beyond original100 principal
is rejected without financial writes. Tests passed4/11.32s with disposable PostgreSQL.

This establishes the tested ADR013/017 separation, not actual banking, legal cancellation,
all supplier-finance concurrency, all cancellation states/roles or populated customer-payment
preservation (customer payments are empty in this fixture). No runtime code/schema changed.

### ADR010 body reconciliation and legacy pinning evidence

Read full ADR010/Documents README, storage adapter, real storage/version/signing tests,
complete/download application methods and download-race tests. MinIO inspection stats then
hashes that exact version; signing uses a selected immutable version and five-minute lifetime.
Real-storage test reuses an accepted PUT URL, then verifies original downloaded bytes and
historical/current replacement contents and filenames. It also checks pending replacement
removes checklist satisfaction and finalized targets reject pending completion/replacement.
This uses real MinIO with scripted scan completion, not malware-engine acceptance. Existing
review-race tests assert no DB connection held during signing and reject revoke/pointer/title
changes before returning a newly signed capability. Already issued URLs retain their lifetime.

Located an untested legacy completion branch: unpinned UPLOADED/SCANNING/AVAILABLE versions
revalidate original expected metadata and append pinning evidence once. Added dedicated
test_document_legacy_pinning.py:11 passed19.21s with disposable PostgreSQL and an explicit
storage double. It checks original metadata retention, repeat no-op evidence, unpinned download
rejection, inspection outside DB sessions, size/hash/MIME/null-version denial and independent
activity/audit/outbox rollback. This is application-branch evidence, not real legacy object
migration or production bucket deletion protection. No runtime code or schema changed.

Actual adapter rejects mutable null-version objects with ValueError before content download;
service-level invalid-version tests use the protocol double. They do not establish HTTP error
normalization for a real unversioned object. Production denial of object-version deletion,
untrusted-file scanning and audited migration of legacy unversioned binaries remain separate
operational requirements; no production policy or binary transformation was performed here.

### ADR009 state and transaction matrix supplement

Read the full ADR009, Export README, services, routers, schemas, models, repositories and
existing vertical tests. Added independent test_export_acceptance_matrix.py expectations
for all6 customs states x5 commands and all7 refund states x6 commands. Cases/documents are
created through existing services, then disposable-only state preparation isolates each pair;
the original vertical test remains the evidence for the complete normal command chain.
Successful transitions check persisted status/version/actor/manual facts and exactly one
activity/audit/outbox each. Denials compare the complete case row and evidence counts.
All11 transitions and both follow-up commands inject failures at each of the three evidence
tables (39 failure scenarios), checking no partial case or evidence writes. Initial19 tests
passed37.46s. Later additions require their own final run result in V1_STATUS.

Added six-role HTTP checks for all11 transitions (66 combinations), direct-service denials,
all11 foreign-ID and stale-version HTTP checks, and set/clear follow-up behavior across all13
states. These are fixture memberships, not six real Logto users. Creation permissions/refund
creation rollback, every checklist replacement/deletion combination, all malformed manual
facts, concurrent source changes and exhaustive navigation remain separately unproven.
No runtime business code, schema, legal submission or external adapter changed in this slice.

### ADR008 body inspection supplement: receivable lock ordering

Read full ADR008/009 and Finance/Export READMEs; inspected full Receivable/Payment repositories,
payment allocate/reverse/order-lock code, full OrderCompletionService and refresh_statuses.
Allocation/reversal lock payment then UUID-sorted orders then UUID-sorted receivables. Completion
locks its order first but ReceivableRepository.locked_for_order orders by receivable_number;
refresh_statuses locks up to500 eligible rows by ID without order locks. This is a concrete
different-order locking seam: refresh and completion can overlap on multiple eligible receivables
whose numbering differs from UUID order. No deterministic concurrent reproduction or correction
has yet run; do not claim deadlock observed, or dismiss it based on existing allocation tests.
Targeted search found no refresh_statuses/locked_for_order concurrency tests. Preserve source
unchanged during the running full regression; subsequent regression/fix requires separately
identified evidence. Existing financial rounding/state/waiver tests were inspected, not replaced.

Subsequent deterministic blocking probe confirms the inversion with LockNotAvailable on a later
UUID while the original order query waits on the first. Fixed lock acquisition to UUID ordering,
retaining business-number response order after locks are acquired. Targeted lock/finance21 passed
34.73s. This supersedes "not reproduced/corrected" above; full command-level completion-vs-refresh
load and final-current full regression remain separate. Earlier full run24118 predates this fix.

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
