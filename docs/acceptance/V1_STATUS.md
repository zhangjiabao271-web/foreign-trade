# V1 acceptance work ledger

This is a progress record, not a release certificate. The implementation guide remains authoritative.

## Sales real-session checks and finance command UI fix: 2026-09-07 19:31

Sales verified completed quotation/order/purchase/shipment/refund views: commercial identifiers,
sales revenue and fulfillment visible; costs/profit and unreviewed source/history/files protected.
OrderFinance incorrectly displayed unauthorized financial commands. Added current session member
permission gates independently for each command, retaining receipt search and archive status.
Seven new permission cases failed before the fix; targeted14 and full frontend237/42files pass,
TypeScript/ESLint pass. Web build/config/deployment and health endpoints pass. Deployed manifest
492b4f128ffca749fdcd9ca94dc862fac8118c5ce9ea3dadfa5a698eeace7219; real sales reload confirms
record/allocate/reverse controls absent with protected reads intact. No business writes or grants.
No full Playwright/backend rerun this step. Manager exact-content disclosure acceptance and wider
role/full-guide evidence remain open. See REAL_IDENTITY.md for scope; not a release certificate.

## Real-session synthetic refund finalized: 2026-09-07 19:15

REF-2026-000001 is REFUNDED after user-provided invoice/BOL became AVAILABLE with no missing
documents. Original manager session completed ready/submit/process/receive, with explicit
nonproduction reasons. Read-only organization-scoped PostgreSQL verification confirms expected
100 CNY, synthetic receipt90, retained difference10, both dates Sep7 and
SIM-REFUND-SUBMIT-20260907-A. All six lifecycle audits belong to the original manager and each
has exactly one matching activity and outbox event by organization/object/action/correlation.
Final UI removes business/follow-up/upload/replacement writes and retains evidence/history and
independent review. No government submission, bank receipt, legal entitlement or disclosure.
This supersedes earlier missing-refund-evidence checkpoints, not the remaining role matrix or
full-guide acceptance gates. No code or infrastructure changed in this step.

## Checklist fix deployed to acceptance Web: 2026-09-07

After observing no active file transfer, deployed only trade-fresh-acceptance-web using the
verified image manifest9021183c0c7dc6d5850984dfb6074189d3ee333db80b5b5ea73e3405ac1ed8c4.
Initial preflight safely stopped before any change because image.Id was compared to the build
config digest; read-only inspection confirmed Docker exposes the manifest-list digest instead,
matching the recorded build output. Corrected exact comparison, config --quiet passed, then
up --no-deps web succeeded. Reused existing identity secrets only in process memory; no secret
output, other service recreation, orphan cleanup or volume removal. Container healthy,
Web health/platform-health200; refreshed original manager session still reads refund case and
privileged controls. Existing refunds evidence remains missing, no business status changed.
This supersedes earlier undeployed notes; no new real-user shipment upload was created solely
to retest the terminal order. No-reload behavior is covered by the explicit browser regression.

## Real-session synthetic clearance/refund setup: 2026-09-07

CUS-2026-000001 advanced through explicit simulated submission (SIM-CUSTOMS-SUBMIT-20260907-A)
and Sep7 clearance. UI terminal controls removed, documents/history retained; no actual government
submission. Created REF-2026-000001 / e9d8a379-cfa0-49ec-894f-2109fdc556e2 for that case,
arbitrary synthetic100 CNY estimate, no legal entitlement or receipt claimed. NOT_READY;
requires separately linked commercial invoice and bill of lading. Synthetic BOL fixture prepared,
awaiting uploads. Follow-up organization-scoped read-only source check confirms CLEARED,
exact submission/clearance dates and reference; linked refund NOT_READY,100 expected/0 received.
All six case-command audits are by the original manager, each with matching activity1/outbox1.
No duplicate readiness success evidence from the earlier missing-document rejection.
Refund document links currently0; attachment acceptance and later nodes remain open.

## Shipment checklist refresh fix in verification: 2026-09-07

Root cause: shipment documents poll until processing finishes, but upload-success invalidation
happens before the async scan result; the independent shipment checklist is never refreshed
on that later result. Added focused effect that invalidates only the selected shipment when
document query data changes. Backend remains readiness authority; no document self-invalidation,
schema, API or business-state changes. code-simplifier review kept the existing query ownership.
UI/UX review limited changes to truthful asynchronous feedback, not page redesign.

New actual-query polling tests first failed2 as expected (shipment reads remained1 after both
AVAILABLE and REJECTED); after fix targeted23 passed and full frontend230/42files passed.
Direct pnpm exec eslint resolution failed; normal lint script used for verification instead.
Normal full eslint and TypeScript commands completed with exit0; formatting passed.
Acceptance Web image build completed successfully (config d5193490110bf3a4545d4afbf74b164b1b2be388214bffb253a32081977fa55a).
Running Web not replaced yet to avoid interrupting user uploads; deployed browser verification
and full browser regression for this fix remain outstanding.

Follow-up: full browser31 passed (3.3m, exit0) with this hook fix. Uses the disposable
trade_workbench_e2e database on the main development cluster (confirmed absent before setup),
not the preserved same-named commercial database in trade-fresh-acceptance. Dedicated object
bucket trade-browser-regression-20260907-checklist retains synthetic uploads; teardown removes
only the transient test DB and ownership-verified test processes. Existing user/recovery data
untouched. Added explicit no-reload checklist assertions after both new-file and replacement
processing; targeted commercial rerun passed1 (2.6m, exit0), explicitly proving both
checklist updates before reload. Running acceptanceWeb is still the previous image;
deployment/real-session smoke remain, rather than claiming build-only deployment.

Customs continuation: the correct commercial invoice subsequently arrived. Both case files
match original synthetic hashes, expected/actual size and checksum, with pinned storage
versions. Actual case UI now shows no missing files; explicit nonproduction ready reason
submitted successfully, CUS-2026-000001 is READY. No government submission performed.

User reported customs upload; source read-only check currently finds only one PACKING_LIST,
AVAILABLE and pinned with the correct packing-file hash. COMMERCIAL_INVOICE is still absent
for CUS-2026-000001. No duplicate case created; current page retained for the missing upload.

## Real-session manual customs checkpoint: 2026-09-07

Created synthetic CUS-2026-000001 / 6c7fb5a7-fa1f-45da-a4fb-26ca07e1f069 for the
delivered shipment,1250 CNY and Sep7 follow-up, explicit nonproduction/no-authority-submission
notes. Real UI prepare succeeds; missing invoice/packing evidence prevents ready as expected.
Original shipment documents do not automatically satisfy separate case links. Current case
awaits its correct synthetic attachments. No real customs submission, clearance or refund.

## Same real-session synthetic order completed: 2026-09-07

Observed rejection of completion with875 unpaid and no waiver. Recorded explicitly
synthetic PAY-2026-000002 for875 CNY, SIM-BALANCE-20260907-A, then allocated exactly875
to the balance. Both receipts show available0. Completion without waiver succeeded.
Read-only source verifies COMPLETED,1250 total,734.10 cost snapshot,515.90 expected profit;
deposit375 and balance875 bothPAID with exact signed net allocations. One manager completion
audit has matching activity/outbox each1. Not actual bank movement or realized profit.
Full V1 remains open, including export tracking, broader real-role acceptance and the
observed asynchronous shipment document-checklist refresh defect.

## Corrected invoice and simulated delivery: 2026-09-07

User replaced the incorrect invoice; original V1 retained, correct invoice V2/V3 both
AVAILABLE with matching source hash/size and pinned storage versions; current UI is V3.
No inference about why two replacement versions were created. Packing V1 unchanged.
After reload, checklist is complete. Before reload the document list was AVAILABLE but
shipment checklist stale: an observed UI refresh defect remains to diagnose and fix.
Real session advanced the synthetic shipment through seven nodes to DELIVERED using
SIM-BOOKING-20260907-A. Final UI disables milestone changes and removes upload/replacement.
No real shipping or customs submission. Tail payment/order closure/full acceptance remain.

## Upload arrived; invoice content correction required: 2026-09-07

The real shipment now has two AVAILABLE, immutable-storage-pinned document versions.
Both expected/actual size and SHA256 match, but both uploaded files are the synthetic
packing list, including the one categorized COMMERCIAL_INVOICE. Compared source file
hashes with persisted actual hashes; invoice content acceptance fails. User has been
asked to replace only the commercial invoice through versioned upload. Latest read-only
check still shows both V1 and no replacement. No shipment milestone or disclosure advanced.
See REAL_IDENTITY for exact hashes. This supersedes the earlier zero-attachment blocker,
not full shipment, malware scanning or V1 acceptance.

## Real manager procurement and upload configuration checkpoint: 2026-09-07

The same synthetic order now has PO-2026-000001 CLOSED: 10 set ordered/received,
73.41 CNY unit cost and 734.10 total. Six purchase command audits each occur once
under the real manager. PROCUREMENT_PREPARATION is DONE. Shipment SHP-2026-000001
is PLANNING with invoice/packing-list gaps; no actual logistics or supplier payment.

Browser upload inspection found inherited localhost:9000 points to the main MinIO,
while acceptance MinIO had no host port. Added optional acceptance-storage.compose.yml:
loopback9300 maps to existing acceptance MinIO, API signs localhost:9300. Only those
two containers recreated, original volume retained, Web session untouched. Compose
validation, formatting, healthy API/MinIO and storage/Web HTTP200 verified.
No actual browser upload or immutable-version acceptance is claimed yet.

Two clearly synthetic TXT attachments are prepared under docs/acceptance/fixtures.
File-picker automation could not isolate a dialog; reading the whole Edge window
was rejected because unrelated private tabs are present. No workaround attempted;
user file selection/upload is the current handoff. Full V1 acceptance remains open.

## Real manager synthetic order/deposit checkpoint: 2026-09-07

Existing accepted-quote journey advanced through explicitly synthetic customer-review evidence and
acceptance. Original opportunity nowWON. Created order dec63e43-7896-413f-b0c0-b2b5939a60a3 /
SO-2026-000001 from acceptedV2,1250CNY,734.10 cost,30%/375 deposit. Manager confirmation opens
procurement preparation; source read-only check proves exact accepted-version/cost/text snapshots
and unreleased order prose. Generated375 deposit dueSep7 and875 balance dueSep14. Synthetic
PAY-2026-000001, referenceSIM-DEPOSIT-20260907-A and explicit no-bank-transaction note, recorded375
and allocated to deposit. Real UI shows deposit paid, payment available0 and orderEXECUTING.
No waiver, real bank action or external customer commitment. Procurement/remaining payment/
shipment/document/completion still outstanding in this real-login fixture; do not claim fullV1.

## Explicitly authorized simulated quotation send: 2026-09-07

User explicitly authorized the nonproduction send. Real manager UI changed the existing V2 to
SENT at2026-09-07T08:57:49.47523Z. Read-only verification confirms one manager send audit and
one matching activity/outbox, unchanged monetary snapshots and unreleased text metadata.
Running worker tasks.py hash matches inspected source; quotation.sent uses receipt-only default
handler, not an email integration. This closes the prior send-authorization blocker, not customer
acceptance, downstream order or whole V1 acceptance. See REAL_IDENTITY for continuation.

## Real manager quotation approval: 2026-09-07

Same synthetic V2 was read through real manager login:1250CNY sales,734.10 cost,515.90 profit,
41.27% displayed margin and original confidential description. Manager approved via UI;
read-only DB confirms exact manager approved_by and one matching audit/activity/outbox.
Costs and unreleased text metadata unchanged. Attempted simulated send was rejected by tool
safety review; no workaround executed. DB still INTERNAL_REVIEW, sent_at null, no send audit.
Explicit user confirmation for this concrete nonproduction send is required. Manager session
remains on the quote page. See REAL_IDENTITY; full V1 is still not accepted.

## Real sales cost-bearing quotation checkpoint: 2026-09-07

Real sales login confirmed A-only selector; synthetic product identifiers visible, unreleased
cost-bearing description hidden, privileged authoring/review controls absent. Created inquiry
585aad47-0857-4f9b-b555-588fc78bc7b4 and quotation bdc024ff-2c12-4f66-baef-6bd68de8a61e:
V1 10x120CNY, V2 10x125CNY, V1 superseded and V2 submitted for internal review. Sales UI hides
cost/profit and original text throughout. Read-only source DB proves both73.41 unit costs,
734.10 total costs and exact original descriptions survived; all three quotation actions are
attributed to real sales with matching audit/activity/outbox. No outbound send or approval.
Manager login now required for the privileged half; no raw authenticated response capture or
complete commercial-role matrix claimed. Exact continuation in REAL_IDENTITY.md.

## Current-user encrypted joint recovery implemented: 2026-09-07

User chose Windows CurrentUser encryption, with cross-machine disaster recovery deferred by
explicit choice. DPAPI binary backups now captured without plaintext backup files; source services
resumed after capture. Restore v2 preserves original bootstrap grantors:46 identity-business tables,
45 commercial tables and79 Logto tables match full-row fingerprints; exact role/password/grant
definitions match;8 original object versions and8 AVAILABLE pointers match. Application reads verify
one completed order, settled installments, manager/operations cost policy and foreign404.
Original bootstrap mismatch failed twice in the first isolated target; that target is stopped and
retained, not cleaned or overwritten. Restored sales session/converted lead and confidential prose
verified. User completed fresh restored manager login: A/B selection, A converted lead v5/five
activities and review controls, B empty list/exact LEAD_NOT_FOUND/no create controls verified.
ReturnToSource completed: original Web3300 and Logto3001/3002 own their ports again; both Web
health endpoints200, original API/Worker healthy, browser B denial persists after reload.
Restored Web/API/Logto/Redis stopped; all volumes retained. DPAPI helper nine checks include1MiB
duplex transfer. This closes local joint identity recovery, not real commercial role matrix,
production deployment or cross-machine disaster recovery. See JOINT_LOCAL_RECOVERY.md.

Additional read-only schema comparison passes for all three restored databases against their
encrypted archives: retains schema/function/owner/object-ACL/comment SQL, normalizing only the
observed equivalent enum-array casts and generated dump headers/psql guards. No restore SQL was
executed and no source endpoints switched. Pure comparison regression10 and DPAPI9 pass;
Prettier direct local invocation succeeds after the pnpm executable lookup failed.
Real manager also created one explicitly synthetic cost-bearing product in source organization A;
sales login is still required for its real-session confidentiality proof (REAL_IDENTITY).

## Identity matrix evidence audit after real sales login: 2026-09-07

Inspected actual assertions and reran five identity groups: auth_unit, oidc_algorithms,
tenant_isolation, identity_administration, identity_acceptance_fixture. 102 passed44.49s,
exit0, with TestClient deprecation and denied pytest cache-write warnings. Real RSA/P-384
signature validation uses supplied test JWKS; membership/role/rollback assertions use temporary
PostgreSQL. No live user was disabled or promoted. Exact requirement mapping is in REAL_IDENTITY.
Read-only inventory confirmed two source business DBs (real identity and complete commercial
fixtures), the existing Logto volume and stopped retained commercial restore containers.
Joint recovery must preserve all of these, not substitute an identity-only empty-business restore.
Credential-bearing backup protection still awaits the user's choice; no identity dump created.

## Real sales login and conversion: 2026-09-07

Sales logged in through Logto with user-entered password. Selector showed only A, not B.
Lead identifiers readable; source/notes/all activity text confidential and review controls absent.
Real sales UI completed qualify/contact/respond/convert to CONVERTED/v5; persisted company,
contact and opportunity IDs and all four sales actor/audit/activity/outbox relations verified.
Missing/fabricated callback state returned400 LOGIN_CALLBACK_INVALID, cross-origin write403
ORIGIN_DENIED, anonymous business read401 SESSION_EXPIRED on actual acceptance Web; these
separate HTTP probes carried no user cookies/tokens. See REAL_IDENTITY.md for exact scope.
No business code or permissions changed this turn. Joint initialized Logto recovery and
real cost-bearing commercial-role matrix remain open. Asked user to choose protection for
credential-bearing identity backups before writing them; no identity backup has been created.

## Real manager login and lead UI permission correction: 2026-09-07

Real Logto manager login, initial unmapped-user denial, explicit one-time synthetic membership
bootstrap and A/B selection now observed. A real UI-created lead is absent from B's list and
its exact detail URL returns LEAD_NOT_FOUND. Found and fixed visible creation controls for
VIEWER; updated only acceptance Web preserving session credentials and data, then verified
both creation controls absent in B. Durable actor/audit/activity/outbox independently matched.
Full frontend 228 tests passed; lead browser subset 6 passed, followed by final full browser
31 passed (3.0 minutes, exit0) after separate conversion permission gating. Final TS/ESLint,
format, client drift, Ruff/mypy and Web image build/healthy checks passed. Real manager logout
returned the workbench to sign-in; next login displayed credentials form and was handed to user
for the sales test account. See REAL_IDENTITY.md for exact
IDs, bootstrap boundaries, deployment and remaining checks. Older setup notes below are history;
real sales login and initialized identity recovery are still open, not full V1 acceptance.

## Real identity setup resumed with user authorization: 2026-09-07

- User confirmed entering the application secret into the independent input window.
  Live Docker inspection now confirms acceptance API/Web/Worker/PostgreSQL/MinIO/
  Redis healthy, migration exited0, beat running; retained commercial restore
  containers remain stopped. Both localhost3300 health endpoints returned200.
- Real Edge navigation from localhost3300's login link reached local Logto sign-in
  for application3h8workreqipkalzznnnq (not the test issuer). Manager username prepared;
  user takes over password entry and sign-in. No business membership has yet been
  added; first check should prove unmapped-user denial, not silently provision access.

- User reports both test-user passwords set. Prior exec PTY50590 remained waiting
  for an application secret, but open-in-app returned only queued and the user saw
  no terminal. That PTY was explicitly interrupted and exited1; no startup claimed.
- Prepared temporary user-operated masked-input launcher under tmp (no secrets),
  syntax and fixed-target CheckOnly passed. Launched separate visible-requested
  PowerShell PID36200, start2026-09-07T12:01:12.8818749+08:00; process confirmed
  alive, but returned main-window handle0/title empty, so user-visible display is
  not proved. Asked user to confirm the window; do not spawn duplicate prompts.
  Launcher uses a named mutex, process-only secret injection and finally cleanup;
  it runs only the three acceptance Compose files and never prints merged secrets.

- Added identity-acceptance.compose.yml as the third overlay after fresh, with
  fixed local issuer/ES384/business audience, callback base localhost:3300, host
  gateway resolution and test bearer disabled. Credentials are required separate
  process variables; no real secret or password written into source.
- Actual Docker Compose merge checked using dummy credentials: isolated project
  and business DB, no API/DB/Redis/MinIO host ports, only loopback Web3300, no new
  Logto services, explicit ES384 and empty E2E_AUTH_MODE. Removing each required
  credential independently produced the expected interpolation refusal.
  Docker printed a sandbox warning about its user config being unreadable; merge
  and assertions passed. No container was started and no runtime acceptance claimed.
  Formatting passed; narrow simplifier review added no abstraction or dependency.

- User confirmed console login and local test-user/application configuration, then
  confirmed the credential-creating application action. Browser inspection already
  showed the created Traditional Web application; no duplicate was created.
- Application: 外贸工作台 · 本机验收, ID3h8workreqipkalzznnnq. Saved and visibly
  verified callback http://localhost:3300/api/auth/callback and post-logout
  http://localhost:3300. No wildcard redirect, management grant or token exchange enabled.
- Created API resource 外贸工作台 API · 本机验收, IDsj37t5u0zie7ywb0pijod,
  identifier https://api.trade-workbench.local. No additional scopes/roles granted.
- Created local identities trade_acceptance_manager (subject vut537xc2tc5) and
  trade_acceptance_sales (subject zwlpm3e6qz30), with no email/phone or business
  membership. Initial hyphenated username failed validation before creation;
  underscore usernames succeeded. Names do not grant application business roles.
- Logto generated masked user passwords; neither revealed nor copied. User must
  take over password setting. Application guide initially rendered its generated
  client-secret example; no secret is copied into this ledger or source files.
  Subsequent guide observations redacted credential values before output.
- Runtime connection, business membership setup, actual redirect login/logout,
  negative identity checks and initialized identity recovery remain unverified.
  Existing main business environment and recovery evidence were not modified.

## Post-0033 complete regression and identity recheck: 2026-09-07

- Full API/Worker regression started against current0033 sources; it is not yet a
  passing result. Follow the live process to completion before quoting totals.
- Final result for that same process:976 passed,1 test-client dependency deprecation
  warning in1210.60s (20m10s), exit0. This is a single complete API/Worker run on0033,
  including the final organization-scoped AI review lock queries. It supersedes
  the pending result above, without claiming real-provider or initialized identity recovery.
- Full repository Prettier initially found quotation-lifecycle.spec.ts formatting;
  automatic formatting corrected that one file with no test logic change. Full
  Prettier, TypeScript and that file's ESLint then passed. Final browser rerun
  started after the complete backend run; do not count it as passed until exit.
- That final browser run completed31 passed in2.8m, exit0, after the scoped-query
  refinement and test-only formatting. It used ordinary isolated fixtures, not
  commercial-recovery mode. This closes the earlier browser-before-final-query
  evidence gap. Test issuer/scripted AI remains distinct from real Logto/live AI.
- Post-run cleanup recheck: no listeners on the two test service ports3100/8010;
  ordinary E2E fixture manifest removed by the successful standard teardown.
  Retained commercial recovery backups/volumes were not targeted.
- During this same run, the performance artifact was regenerated at2026-09-06
  23:46:41 UTC: five measured p95 values9.018/10.591/11.650/14.176/26.304ms
  all below their respective500/500/500/800/1000ms limits. Shipment checklist
  queries remain3 SELECTs for both1 and20 rows. GUIDE_18_GATES now cites this
  actual artifact, not the older sample. This is scoped performance evidence,
  not proof that the still-running full regression or real login has passed.
- Current static recheck: Ruff passed,365 Python files formatted, mypy210 source
  files passed, generated OpenAPI/client drift check passed. No code changed.
- Read-only local Logto inspection found both identity containers running, PostgreSQL
  healthy, and users grouped by tenant showing admin=1 with no default-tenant rows.
  This supersedes the historical assumption that no administrator exists; it does
  not prove the account can log in or establish who controls it. No user, password,
  application, membership or provider state was changed.
- Public discovery still advertises ES384. Docker README's stale RS256-only setup
  wording corrected to the explicit algorithm policy already accepted in ADR-012.
  Real redirect login and initialized identity recovery remain unverified; requested
  user login to the existing console and authority for local acceptance setup.
- Subsequent read-only provider check confirms only admin-tenant users/applications:
  users admin=1; applications admin SPA=1 and MachineToMachine=3. No default-tenant
  business users or application rows were returned. Existing administrator presence
  therefore does not prove the workbench login application is configured. No secrets
  or credentials were read, and no provider state was changed. Real-login acceptance
  now requires the user's console access and confirmed local test setup authority.

## Creator-submitted AI disclosure0033: 2026-09-07

- Final closeout: scoped-lock backend rerun56 passed78.94s; final frontend223/41
  passed22.89s, TypeScript/ESLint and Ruff/mypy passed. Final browser31 passed3.4m
  before the backend-only organization-scoped lock-query refinement; that refinement
  was subsequently covered by the56-case rerun and rebuilt runtime, not a new full suite.
  Final375/1440 screenshots inspected. Rebuilt runtime is0033 head with no metadata drift,
  Worker pong and both health endpoints200. Dedicated acceptance containers stopped;
  project-label running list empty. All volumes/backups/recovery evidence retained.
  Main environment not upgraded. Earlier counts below are intermediate checkpoints.

- User explicitly approved the private-submission boundary; ADR-026 and implementation guide
  updated before implementation. New candidate table preserves original runs and every revised
  artifact, with exact-content release, owner/private separation and atomic version/key/evidence.
- Sales/operations cannot bypass prose/cost protection as creators. Only current approved
  artifact is released, no source/tool/approval-copy inheritance. Finance content review does
  not grant task execution. Low-authority task requests bind displayed disclosure ID/version.
- Backend56 passed72.11s, frontend223/41 passed13.71s, static/client checks passed. Browser
  initial16 pass/1 locator timeout/14 unrun; corrected full31 passed3.0m. Isolated0033 build,
  metadata, Worker pong and Web/platform health200 passed. See AI_DISCLOSURE.md for scope.
- Code-simplifier review removed an unused lookup helper, batched run disclosure projections,
  and retained constant-query candidate pagination; no unrelated refactor or dependency change.
  UI/UX review preserved the established styles, explicit confirmations and error/retry states.
- This supersedes older statements that private-draft submission authority is unanswered.
  Whole-V1 acceptance and real identity/model/initialized identity-recovery remain unproven.

## Queue evidence revalidation: 2026-09-07

- Read-only query of retained isolated recovery PostgreSQL confirms restart/broker-loss scenarios
  have1/2 publications respectively, exactly1 intended consumer receipt each, and matching event
  result references. Generic sample jobs remain PENDING by design: consumer records the receipt
  reference only, not a completed business operation. No Redis/worker start, duplicate execution,
  fixture writes or queue deletion occurred. Database stopped afterward, volume retained.
- Current platform transaction and worker task suites21 passed11.91s. This supplements the
  historical real-broker rehearsal, not a newly executed fault exercise. See GUIDE_18_GATES.
- AI private-draft review still awaits explicit creator-submission authority; real Logto setup
  and initialized identity recovery remain unresolved. No overall acceptance claim.

## Full commercial PostgreSQL/MinIO recovery: 2026-09-07 (slice verified)

- Retained isolated browser fixture:31 passed3.0m. Custom PostgreSQL dump and cold versioned
  MinIO volume restored to independent empty targets;45 table fingerprints,8 exact object
  versions, complete commercial chain, settled deposit/balance and application role/tenant
  projections match. Alembic check clean at0032.37 CHECK text differences were confirmed
  equivalent by PostgreSQL reparse in rollback-only temporary tables, not ignored.
- Final recovery tests13 passed1.27s; Ruff and mypy210 passed. Review kept narrow fixed-target
  guards, immutable evidence and explicit comparison; no business schema or permissions changed.
  Evidence and SHA-256 are in COMMERCIAL_RECOVERY.md and backups/20260907-commercial-recovery.
- PowerShell syntax, Compose config and formatting361 files passed. All dedicated services
  stopped; Compose running list empty. All source/target volumes and backups retained, main
  environment untouched. No material data deletion occurred.
- This supersedes historical statements below that full-commercial DB/object recovery is open.
  Initialized Logto restore, real login and private AI disclosure remain open. Test issuer and
  synthetic isolation witness are not real identity acceptance. No overall completion claim.

## Direct shipment source snapshots: 2026-09-07 (slice verified)

- Additive GET shipments/{id}/source-lines requires shipment.read plus order.read in router and
  service. Sales owns organization-scoped live parent/line lookup and reuses full-order protected
  projection. Narrow DTO contains identifiers/status/SKU/unit and permitted description only;
  no monetary fields. At most200 source IDs, fail404 for any unavailable source, no partial map.
  No migration, dependency, business-state change or read evidence writes.
- Source disclosure is calculated against all active order lines, including unshipped lines.
  Web detail no longer scans cursor pages, distinguishes protected/loading/error text, retries
  directly and shares sales-orders invalidation/session scope. UI/UX review retained existing
  styles and keyboard/error controls; simplifier reused existing projection, removed nested
  conditional rendering and an obsolete type import without unrelated changes.
- Initial source test1 passed4.24s; expanded source/combined-parent tests2 passed6.86s cover all
  six HTTP roles, direct service permissions, tenant/deleted/missing sources,200-ID guard,
  release invalidation from an unshipped line and constant four business SELECTs. Source data
  is unchanged by reads. Local HTTP/real-PG measurement and EXPLAIN plans are recorded in
  test-results/shipment-source-performance.json:30 samples/3 warmups,p95 18.964ms at
  2026-09-06T19:49:48Z; tiny fixture is not production load evidence.
- Frontend219/40 passed17.72s, final TypeScript/ESLint passed after removing an unused type
  import. Targeted browser1 passed20.1s verifies synthetic old source
  direct resolution, protected text, keyboard retry, finalized-parent controls and no order-page
  request;375/1440 screenshots inspected. Full browser31 passed3.9m. API/worker/Web images built;
  isolated0032 head, clean metadata, worker pong, both health200 and quiet Compose validation
  passed. Environment stopped, volumes retained; main unchanged. Related backend65 passed112.40s.
  Ruff/format357, mypy208 and generated client drift passed.
  Final synthetic browser fixture now reports the two genuinely missing documents instead of
  an empty checklist; targeted rerun1 passed13.5s. This fixture is UI evidence, not a real shipment.
- Full backend942 passed1414.29s but was collected before this source addition; it cannot
  certify the two new tests. This is942 baseline plus targeted new-source/related verification,
  not a claimed single944-test full run. AI privacy/real identity/joint restore still block V1.

## Commercial cursor navigation0032: 2026-09-07 (slice verified)

- Shipment/quotation/inquiry/purchase lists now expose scoped live cursors, deterministic
  timestamp/ID ordering, limit+1 sentinels and page-local count/has_more/next_cursor. Inquiry
  retains received_at sorting; status filters remain. Purchases support a sales-order filter
  and batched items. Missing/deleted/foreign or wrong-parent anchors404. Protected DTOs,
  original permissions and read-only evidence behavior remain.0032 adds six active indexes only.
- Web shares cursor collection/controls, explicitly loads50 rows, retains rows on failure and
  resets filter/session scopes. Inquiry selection shows identifiers without prose; purchase
  commitments remain unavailable until all pages load. Code-simplifier review preserved the
  shared dedupe/control helpers and avoided unrelated abstractions.
- Targeted commercial/order navigation4 passed97.56s, including105 rows/entity, ties, all six
  roles, foreign/deleted/invalid/wrong-parent cursors, exact stored commercial preservation
  across0032 downgrade/upgrade and metadata checks. Separate core migration/navigation4 passed
  42.36s; earlier related regression18 passed70.02s. Synthetic planning shipments are list-only
  fixtures; existing real-line/document shipment regression supplies lifecycle coverage.
- Recorded local ASGI+PostgreSQL benchmark (full rerun,2026-09-06T19:35:17Z),105 rows/entity,
  50-row cursor pages,30 samples after3 warmups: quotation24.421ms, inquiry19.293ms,
  shipment17.856ms, purchase20.779ms p95. Business SELECTs2/2/4/3 respectively. EXPLAIN evidence is in
  test-results/commercial-cursor-performance.json; small fixtures can choose older indexes.
  Reruns overwrite this artifact. This is not production load, network or browser performance.
- Frontend217 tests/40 files passed17.61s; TypeScript/ESLint passed. Full browser30 passed3.1m,
  including synthetic51-row pagination interactions and existing real business journeys.
  Updated375/1440 inquiry screenshots inspected: separated controls, wrapped IDs, no overflow.
  API/worker/Web images built; isolated0032 head, clean metadata, worker pong and both Web
  health200 passed. Dedicated environment stopped, all volumes retained; main unchanged.
- Full backend942 passed1414.29s with verified-new workspace basetemp/cache
  pytest-full-commercial-pages-20260907-0335 / pytest-full-cache-commercial-pages-20260907-0335;
  only the existing Starlette/httpx deprecation warning remains. This run covers0032 but was
  collected before the later source-lines tests above. AI disclosure, real Logto and joint
  recovery remain open; dedicated shipment source resolution now has its own checkpoint above.

## Order cursor navigation: 2026-09-07 (slice verified)

- API adds scoped live UUID cursor, deterministic created_at/id descending ordering, page-local
  count/has_more/next_cursor, and a limit+1 sentinel. Existing protected snapshots and command
  contracts remain.0031 adds the active org/created_at/id index only; no data rewrite/deletion.
- Web explicitly loads50 orders per page, deduplicates IDs, retains records on page failure and
  offers retry/restart. Source selectors in shipment creation/detail share navigation. Selected
  quantities survive new pages. Existing identity-keyed QueryClient isolates caches. UI/UX review
  retained existing styles and keyboard/pending/error feedback; code-simplifier removed an empty
  control wrapper and reused bounded-query/snapshot logic rather than adding a parallel DTO.
- Targeted migration/navigation6 passed39.70s:105 orders, all ties, exact final/empty pages,
  insertion/deletion between pages, foreign/deleted/invalid cursors, unchanged read evidence,
  batch3 SELECTs, and full commercial snapshot retention across0031 downgrade/upgrade. Separate
  six-role cost policy7 passed; related order/procurement3 passed. First fixture failures were
  stale expected versions after test timestamp edits and duplicate fixture SKU reuse; corrected
  the fixtures, not production constraints. Migration test head updated explicitly to0031.
- Local ASGI+PostgreSQL benchmark:105 orders/two lines each,50-row cursor page,30 samples after
  three warmups,p95 18.103ms,3business SELECTs. EXPLAIN ANALYZE/BUFFERS saved in
  test-results/order-cursor-performance.json. This is not production load or browser latency.
- Frontend related64 passed4.40s; full211/38 passed19.94s; TypeScript and ESLint passed. Browser29
  passed4.0m, including cursor recovery/keyboard/older shipment selection with explicit synthetic
  UI pages, plus the existing real business chain.375/1440 retry screenshots inspected: readable
  wrapping, preserved rows and no page overflow. API/worker/Web images built; isolated0031 head,
  clean metadata, worker pong and both Web health200 passed. Main environment unchanged; shared
  local API image tag rebuilt. Ruff/format354, mypy208 and generated-client drift passed.
  Full backend941 passed1307.56s with a verified-new workspace basetemp/cache; only the existing
  Starlette/httpx deprecation warning remains. This run includes order0031, not the subsequently
  developed shipment/quotation/inquiry/purchase cursor changes. Isolated environment stopped with
  all volumes retained.
- Shipment/quotation/inquiry/purchase navigation, AI disclosure, real Logto and joint recovery
  remain separate gaps. Current shipment source detail still needs explicit page loading, not
  dedicated ID resolution. This checkpoint does not certify V1 or upgrade the main environment.

## Shipment milestone preconditions: 2026-09-07 (verification running)

- ADR-025 requires expected_version plus key for book/ready/enter-customs/depart/start-transit/
  arrive/deliver and exposes the existing response counter. Explicit unreleased contract update;
  owned HTTP/service/UI fixtures updated, no missing-guard fallback or schema/dependency change.
- Sorted parent then shipment locks precede action receipts. Matching scoped replay returns live
  current facts/gaps after later progress/finalization without new effects; fresh commands validate
  version, active source mappings, eligible parents and cumulative quantities. Different booking
  references conflict. Existing permissions, pinned document checks, timestamps and Sales-owned
  order progress remain. Business/evidence/key share one transaction.
- UI freezes booking opening version; all actions have stable request identity and explicit retry
  of original variables across refetches. Scope/shipment remount discards identity. Known finalized
  source orders hide new actions. UI/UX review retained existing styles, input/error accessibility
  and made recovery explicit; backend remains authoritative.
- Existing shipment regression30 passed (42.24s). New70 passed (113.24s): all seven actions, six
  roles at HTTP/service, mandatory/stale/identical/conflicting/no-op/later replay, current document
  gaps, tenant/deletion, finalized/pending/deleted/overcapacity sources,21 evidence failures and21
  concurrent key/version races. Expanded lock14 passed (35.22s), adding seven observed waits for
  parent finalization with no partial shipment/key/evidence writes.
- Frontend209/38 passed (16.45s); shipment frontend30 includes seven refreshed-version retry
  cases and frozen pre-submit booking version. TypeScript/ESLint, Ruff/format353, mypy208 and
  generated client drift checks passed. Browser28 passed (3.2m), with committed/lost-response
  recovery for all seven milestones, identical key/body and the same shipment, plus the complete
  order-to-refund chain. Retry screenshots375/1440 inspected: retained booking input, readable
  wrapping and no horizontal overflow. Code-simplifier review kept one backend source validator
  and narrowed the frontend command union to avoid unnecessary casting; no unrelated refactor.
- API/worker/Web images built; isolated startup,0030 head, clean Alembic metadata, worker pong,
  both Web health200 and quiet Compose validation passed. Main environment not upgraded; shared
  local API tag rebuilt. Isolated environment stopped with volumes retained. Full backend939
  finished:938 passed,1 setup error,3 warnings in1148.00s. The sole error is Windows denying
  pytest's existing OS temporary directory before the process-ownership test body. A separate
  rerun with a verified-new workspace basetemp passed1 in0.11s. No ACL changes or old-temp deletion.
  This is not a single green full run and predates order pagination; repeat with a new basetemp
  after the next slice. The earlier850 predates shipment lock/guard work.
- Automatic approval timed out before the first new backend test command started. One retry
  successfully ran the70 tests; this was not a business test failure. Existing Starlette/httpx
  deprecation and unavailable pytest-cache warnings remain non-fatal.

## Shipment lock-order prerequisite: 2026-09-07

- Creation now discovers scoped source IDs, locks active parents in ID order, locks source lines
  in ID order and revalidates the exact mapping before order-state/capacity checks. Deleted parent
  or line rejects with no shipment/number/key/evidence. No unlocked ORM snapshot is cached.
- Seven milestones acquire scoped parent locks in ID order before the shipment lock. Sales still
  owns order milestone writes; timestamps, file requirements, capacity and existing replay behavior
  are unchanged. Milestone version/key and conflicting booking replay remain unfinished.
- First creation13 passed (20.68s); expanded creation14 plus seven milestone lock races, shipping
  progress and document regression total30 passed (45.96s). Competing parent owners demonstrably
  lock lines/shipments while commands wait, with bounded lock timeouts; finalized/deleted sources
  are reread after wait. Combined multiorder reversed-input creations also pass. Ruff/format and
  full backend Ruff/format352, mypy208 and client drift passed. No migration, dependency, API or
  frontend change; no new browser run for this backend-only lock slice. API/worker images built;
  isolated startup,0030 head, clean Alembic metadata, worker pong and both Web health200 passed.
  Shared API image tag rebuilt; main environment not upgraded. Isolated environment stopped with all
  volumes retained.
- Targeted tests warn about existing Starlette/httpx deprecation and unavailable pytest cache;
  neither caused test skips/failures. Full850 below predates this source change and is not its
  full-regression certificate.

## Purchase decision preconditions: 2026-09-07

- ADR-024 explicitly replaces unreleased unguarded approve/send/confirm contracts with displayed
  purchase version and mandatory key at HTTP/service boundaries. Sales-order then purchase locks
  serialize decisions against parent finalization, amendment and source review. Matching scoped
  receipts project original current facts, including after finalization; fresh requests check
  version and reject finalized parents. Confirmation no-ops additionally compare stored supplier
  reference/date rather than silently ignoring changed commitments. No pricing/quantity/migration.
- Original permission boundaries remain: approval needs procurement.approve plus profit.read;
  send/confirm need procurement.write. Timestamps/approver/state/activity/audit/outbox/key commit
  atomically. Owned caller helpers now submit explicit guards without weakening their assertions.
- UI sends displayed versions and stable unchanged-body keys; confirmation freezes its opening
  counter through refetch. Explicit original-variable retry retains action/reference/date/version.
  Fresh controls hide on finalized parent; authorized receipt recovery remains. Existing session
  scoping and ledger styles retained under UI/UX review. No persisted browser keys or external send.
- Existing procurement regression60 passed (109.55s). Initial new48 passed (77.08s); expanded53
  passed (99.11s), adding three observed parent-lock races and two independent text review replay
  cases. Covers all roles at HTTP/service, stale/missing guards, exact/conflicting/no-op replay,
  later progress, finalized parents, tenants/deletion, nine evidence failures and nine key races.
- Frontend202/38 passed (16.90s), TypeScript/ESLint, Ruff/format351, mypy208 and client drift passed.
  Initial browser13 passed / 1 failed / 14 not run (1.3m): the new recovery helper removed its
  route as soon as the pending state hid the retry button, before response fulfillment finished.
  It now waits for the actual target status before removing interception or changing roles.
  Full browser rerun28 passed (3.5m): stale approval rejected, approve/send/confirm each commit then
  lose their response and recover with identical key/body to the same purchase ID; complete
  order-to-refund chain passes. Retry screenshots375/1440 inspected: retained fields, readable
  wrapping and no horizontal overflow. No application authority or business assertion relaxed.
- API/worker/Web builds and isolated startup passed.0030 head, clean Alembic metadata, worker
  pong, both Web health200 and quiet Compose check passed. Isolated environment stopped with all
  volumes retained; main environment not upgraded, shared local API tag rebuilt. Full backend850
  passed (1107.06s), covering ADR-024 before the later shipment lock-order change. Existing
  Starlette/httpx deprecation warning only. The preceding full797 covers ADR-023.
- Code-simplifier review retained existing projection/key primitives, one narrowly shared
  decision-lock/version check and explicit domain branches; no unrelated refactor.

## Sales-order creation request identity: 2026-09-07

- ADR-023 adds optional scoped creation keys and validates a copied canonical request with
  four-place deposit normalization. Matching replay returns the original live protected order,
  including after confirmation; fresh duplicates must match original deposit rate/due date or
  receive ORDER_CREATION_CONFLICT. This explicitly corrects silently ignored conflicting terms,
  including unkeyed calls, without changing the one-order-per-quotation rule or stored snapshots.
  Receipt/number/order/lines/activity/audit/outbox are atomic; no schema/dependency.
- Owned RHF form retains unchanged request/key, rotates edited inputs and blocks synchronous
  duplicates; failed fields and clear recovery guidance remain. Session-keyed remount discards
  local identity. Existing ledger styles retained under UI/UX review; no browser key storage.
- Initial backend42 run40 passed / 2 failed (60.83s): newly staged receipt autoflush preceded
  foreign quotation lookup and raised a membership FK error in direct foreign-context tests.
  Source lookup now delays that flush, preserving404 and transaction rollback. Rerun42 passed
  (57.04s). Expanded creation17 passed (35.58s), including six roles, exact/current-projection
  replay, independent text release/restrict, changed date/rate, invalid keys, tenants/deletion,
  four failure injections and four barrier-controlled concurrency modes.
- Frontend first run198 passed / 1 new-test failure: incomplete mock problem shape did not
  produce the expected server-detail message. Mock corrected;199/38 passed (14.15s).
  Final event-handler adjustment avoids reading retry refs during render; final199/38 passed
  (20.84s).
  TypeScript/ESLint, Ruff/format350, mypy208 and generated-client drift passed.
- Full browser28 passed (3.6m), including committed201 followed by response loss and identical
  body/key recovery of the same order ID through the complete order-to-refund journey. Retry
  screenshots375/1440 inspected: retained fields, readable recovery text and no horizontal overflow.
- API/worker/Web images and isolated startup passed.0030 head, clean Alembic metadata, worker
  pong, both Web health200 and quiet Compose validation passed; isolated containers stopped
  successfully with volumes retained. Main environment not upgraded; shared local API tag rebuilt.
  Full backend797 passed (1029.64s), exit0, against unchanged0030, with the existing Starlette/httpx
  warning. This run imported code before ADR-024 procurement changes; it is not their coverage.
- Code-simplifier review keeps the existing key/number/projection primitives and explicit
  transaction branches. No broad abstraction or unrelated behavior change.

## Mandatory sales-order confirmation preconditions: 2026-09-07

- ADR-022 requires displayed expected_version and Idempotency-Key at HTTP/service boundaries,
  explicitly breaking the unguarded unreleased V1 contract. Tenant order lock precedes key;
  matching replay projects live original order facts, including after later progress. Fresh
  stale requests fail before state rules. Existing allowed-state no-op remains guarded. State,
  timestamp, procurement task, activity/audit/outbox and key remain one transaction; no schema,
  amount, deposit arithmetic, role or completion rule changes. Main deployment not performed.
- Owned UI sends the displayed counter and retains original variables/key for explicit retry
  through background changes. Fresh clicks on refreshed content rotate preconditions/key.
  Detail remounts by order/session/organization; errors retain recovery guidance and permission
  gates. Existing styles are preserved under UI/UX review, not redesigned.
- Existing order/procurement/shipment regression12 passed (20.46s); new confirmation16 passed
  (19.29s), covering both deposit branches, missing/invalid/stale guards, all six roles at HTTP
  and service boundaries, key conflict/current-projection replay, tenant/deletion, four task/
  evidence rollbacks and three concurrency modes. Old fixture callers updated without relaxing
  business assertions. Frontend198 / 38 files passed (15.00s); TypeScript/ESLint, Ruff/format333,
  mypy208 and generated-client drift passed. Full backend780 passed (970.85s), exit0, on
  stable0030. Existing Starlette/httpx deprecation warning remains. This run imported code before
  ADR-023 order creation changes and is not final regression evidence for those later changes.
- API/worker/Web image builds, isolated startup and quiet Compose configuration validation passed.
  Verified0030 head, clean Alembic metadata, worker pong and both Web health200; isolated containers
  stopped successfully with volumes retained. Main not restarted/upgraded; shared API tag rebuilt.
- Initial browser run13 passed / 1 failed / 14 not run (4.7m): stale-version rejection succeeded,
  but the fixture's navigation init script restored the sales actor after reload, correctly hiding
  manager confirmation. The script now explicitly restores the manager actor after that reload;
  no application authority was widened. Full browser rerun28 passed (3.4m), including stale
  confirmation rejection, committed-response loss and exact original-key/body recovery through
  the complete order-to-refund journey. Retry screenshots375/1440 inspected at original resolution:
  controls remain readable, guidance wraps and no horizontal overflow was observed.
- Code-simplifier review kept the existing explicit domain transaction and shared key/projection
  primitives; no broad abstraction.
  The prior full764 below imported code before ADR-022, so is not final coverage of this slice.

## Inquiry creation uncertain-response recovery: 2026-09-07

- Optional tenant-scoped durable creation keys commit with inquiry/CRM/activity/audit/outbox.
  Requests are validated copies; key lock precedes opportunity lock. Matching replay returns
  the current protected original inquiry, including after quotation progress, without recreating
  evidence. Changed payload conflicts; deleted/foreign records fail. Unkeyed legacy calls remain
  independent registrations, and distinct inquiries for one eligible opportunity remain allowed.
- Owned Web form retains the first received_at timestamp and key for unchanged input, rotates
  edited input, synchronously blocks duplicate submission and retains fields after uncertainty.
  Recovery guidance explicitly covers changed input and close/reload limits. No schema/dependency.
- New backend15 passed (23.36s): six roles, HTTP/service and current-state replay, current text
  release/restrict projection, tenant/deletion, three evidence rollbacks and three concurrent modes.
  Frontend197 / 38 files passed (17.24s), TypeScript/ESLint passed. New page test covers synchronous
  duplicate events, pending controls, unchanged body/timestamp/key recovery and edited-input rotation.
  Ruff/format332 and mypy208 passed; generated-client drift passed. Full backend764 passed
  (974.00s), exit0, against stable0030 schema, including the corrected commercial copy-chain
  fixture below. Existing Starlette/httpx deprecation warning remains. This predates ADR-022.
- Full browser28 passed (3.6m): inquiry POST commits, response aborts, unchanged retry returns the
  same inquiry ID using the identical body/timestamp/key; the order-to-refund chain continues.
  Lost-response inquiry screenshots375/1440 inspected: retained input, visible save button,
  wrapped error/recovery guidance and no horizontal overflow.
- API/worker/Web image builds and isolated startup passed.0030 head, clean Alembic metadata,
  worker pong and both Web health200 verified. Main containers not restarted/upgraded; shared
  local API image tag rebuilt. Isolated stop completed successfully with all volumes preserved.
- Code-simplifier review retained the shared durable command primitive and current protected
  inquiry projection, explicit transaction/lock order and narrowly scoped form-local retry state.

## Mandatory quotation decision preconditions: 2026-09-07

- ADR-021 explicitly changes the unreleased V1 submit/approve/send/accept/reject/expire contract:
  required expected version ID, row counter and Idempotency-Key at HTTP/service boundaries.
  No unguarded current-version fallback. Quotation/current locks precede action-scoped key checks;
  acceptance retains quotation-before-opportunity ordering, validity and CRM-owned winning rules.
  Receipt commits atomically with domain/evidence changes. Exact replay returns the original live
  version through current-role projections, including after revisions, without repeating evidence.
- Owned page sends displayed preconditions and retains submitted variables/key for explicit retry
  after background changes. Fresh decisions use fresh displayed data; scoped remounts clear local
  state. Generated client and test callers now use the mandatory protocol. No schema/dependency.
  Main deployment requires simultaneous caller upgrade; it has not been performed.
- Existing quotation/cost/validity/opportunity regression41 passed (44.99s). New matrix initially
  47 passed / 7 failed (55.79s): existing generic accept/reject route shadowed /expire and produced
  path validation422. Explicit expire route now precedes that generic route. Entire matrix54
  passed (55.84s): all six actions, omitted/invalid/stale guards, identical/conflicting replay,
  live permissions/tenant/deletion, later revisions, 18 evidence rollback and 12 concurrency cases.
- TypeScript/ESLint passed; frontend196 / 38 files passed (15.14s), including explicit retry that
  retains the old version/key after background V3 data, then a new V3 decision with a new key.
  Ruff/format331 and mypy208 passed. Full backend749 finished with unchanged0030 schema;
  see the actual split-run result below, not an all-green claim.
- Full browser28 passed (3.6m): an independent confidential text review increments the current
  row counter; the unchanged old page's submit is rejected with VERSION_CONFLICT. After reload,
  submit commits but loses its response; explicit replay sends the original version/counter/key
  and recovers INTERNAL_REVIEW. The full order-to-refund chain and remaining role journeys pass.
  375/1440 state-retry screenshots inspected with visible controls, wrapped recovery copy and no
  horizontal overflow. Source disclosure remained restricted during stale-view setup.
- Client drift, all API/Web/worker/beat image builds and isolated startup passed.0030 head and
  clean Alembic metadata, worker pong and both Web health200 verified. Main containers were not
  restarted/upgraded; shared local API image tag rebuilt. Isolated stop completed successfully
  with volumes preserved. These checks do not close AI/private review, real login or joint recovery.
- Code-simplifier review retained explicit permission and domain transactions, sharing only the
  action-key/precondition/replay protocol. The existing read projection is reused, not cached
  privileged output. No broad state-machine rewrite or frontend authority duplication was added.
- Full backend has reported one failure so far: commercial copy-chain test still called old
  two-argument state methods. A targeted reproduction confirmed the missing required request,
  not a domain failure. Its calls now pass exact current preconditions and distinct operation
  keys; acceptance retry deliberately reuses the original request/key. All text-copy and hidden
  response assertions remain. Targeted copy-chain passed (3.82s); Ruff/format passed. Full
  commercial review54 passed (90.77s), exit0. The original749 process imported that test before correction:
  final result748 passed / 1 failed (956.64s), exit1, solely this old missing-request call. Latest
  full764 includes the correction and new inquiry cases and passed (974.00s), exit0.

## Quotation creation uncertain-response recovery checkpoint: 2026-09-07

- Creation now records tenant-scoped request hash and quotation ID atomically with the existing
  snapshot, number, inquiry/opportunity progress and activity/audit/outbox. Key lock precedes
  inquiry/opportunity locks. Matching replay locks the live owned quotation and returns current
  protected versions; it neither reprices nor creates new evidence. Explicit-cost permission is
  checked before replay. Existing unkeyed callers still issue a new command and receive the
  original one-quotation-per-inquiry conflict on duplicate creation; no silent deduplication.
- Owned form retains an unchanged-input retry key, rotates edited input, synchronously guards
  duplicate submission and explains recovery and close/reload limitations. Existing styling,
  session remount, field validation and backend-only authority remain. No migration/dependency.
- New creation9 plus existing revision/cost group31 passed (31.13s), covering conflicts, scoped
  service/API permissions, current-version recovery, cost/deleted-resource replay denial,
  activity/audit/outbox rollback of key/number/CRM state and three concurrent request modes.
  Ruff/format329 and mypy207 passed; regenerated API client includes the optional creation header.
- Frontend195 / 38 files passed (20.11s), TypeScript passed. Initial ESLint rejected passing a
  ref-reading callback directly through handleSubmit during render. The form now invokes that
  handler from the actual submit event; no disabled rule or changed retry semantics. Final
  TypeScript/ESLint passed; frontend195 / 38 files passed again (17.83s).
- Full browser28 passed (3.7m): creation commits, its response is deliberately lost, and unchanged
  retry opens the exact committed quotation ID with the same request key. The remaining complete
  order-to-refund journey passes.375/1440 retry screenshots inspected with visible wrapped
  recovery text and controls and no horizontal overflow. Final fixed-source primary rerun passed
  (1 test,2.4m), including quotation lost-response recovery and the order-to-refund business chain.
- All service images built; Web rebuilt after the submit-event static correction. Isolated
  startup,0030 head, clean Alembic metadata, worker pong and both Web health200 passed. Isolated
  containers stopped successfully with volumes retained; main containers not restarted/upgraded.
  Shared local API image tag rebuilt. Client drift passed. Full backend695 passed (949.46s),
  exit0, with unchanged0030 schema and the existing Starlette/httpx warning. This run also includes
  the corrected procurement fixtures and history filtering; no whole-V1 acceptance claim.
- Code-simplifier review reused one current protected quotation response loader for read/replay
  and retained explicit creation transactions and lock ordering. UI keeps the existing design;
  accepted FastAPI command architecture overrides the generic skill's Server Actions suggestion.

## Procurement source/history confidentiality checkpoint: 2026-09-06

- 0030 adds nullable purchase review metadata and tenant reviewer constraints without rewriting
  descriptions/cancellation evidence. Populated downgrade refuses data loss. Source projections
  cover list/detail and all existing command/replay return paths. Exact parent/line versions and
  content digest invalidate release after receipt or content restoration; replacements do not
  inherit approval. Review locks sales order then purchase, preserving command lock order.
- Supplier confirmation numbers remain identifiers, with cost/profit entry prohibited. The legacy
  cancellation evidence field and historical receipt reference accept prose and remain reviewed.
  Purchase histories now support independent Work review under procurement.read plus profit.read.
  Known structured command-result prices stay hidden even when history prose is released; source
  disclosure never releases amounts or histories, and history review never releases source text.
- Initial existing purchase/migration group33 passed (48.76s); new source group12 passed (22.14s).
  Expanded group initially21 passed / 6 failed because a new history fixture omitted its required
  correlation_id, not due to a production rule. Fixture corrected; source/history/cost group27
  passed (50.35s), including six roles, API/service/replay, parent/tenant/right checks, races,
  line restoration, evidence rollback, replacement independence and0029 preservation/downgrade.
- Frontend194 / 38 files passed (13.96s), TypeScript/ESLint passed. Ruff/format328, mypy207 and
  generated-client drift passed. Code-simplifier review retained explicit domain transactions,
  reused the existing review form and replaced source permission selection with a typed map.
  No dependencies added; accepted backend-command architecture overrides generic skill advice.
- Browser28 initially passed (3.2m) with procurement source hidden/review/released alongside five
  commercial groups. Expanded full browser28 passed (3.1m), adding historical receipt review and
  proving purchase source stays confidential after history release.375/1440 source and history
  screenshots inspected: wrapped content, visible controls and no horizontal overflow.
- Full backend686-case run finished:680 passed / 6 failed / 1 existing Starlette/httpx warning
  (855.17s), exit1. All six failures are the history fixture's missing correlation_id: this
  already-running process imported the fixture before its correction. The corrected27-case
  source/history/cost run above passes; this is split-run evidence, not one all-green full run.
  After full-suite termination, the latest source/history/cost27 tests passed again (41.14s),
  exit0; focused Ruff and format14 also passed. Schema0030 remained stable throughout.
- All API/Web/worker/beat image builds and isolated0030 startup passed; after history amount
  hardening, API/worker/beat rebuilt. Alembic head/check, worker pong and both Web health200 passed.
  Main containers were not restarted/upgraded; shared local API image tag rebuilt. Isolated stop
  completed successfully with volumes preserved. Whole V1 and real identity/joint recovery are
  not complete. AI creator-private review workflow choice requested without blocking other work.

## Commercial source-text confidentiality checkpoint: 2026-09-06

- 0029 adds nullable tenant-bound review metadata to products, inquiries, quotation_versions,
  sales_orders and sales_contracts; preserves all existing text and refuses populated downgrade.
  Service projections protect original descriptions, quote/order terms and line descriptions,
  contract notes/nested snapshot text. Names/SKU/unit, RFQ and external contract numbers remain
  identifiers under the user's explicit policy; internal cost/profit entry there is prohibited.
- Independent review requires original read plus profit authority, exact version/digest and
  confirmation/reason/key with atomic evidence. Quote/contract parent-first locks are retained.
  Item versions participate in the digest; restored original item text cannot revive disclosure.
  Backend copies original immutable facts; new records/revisions never inherit source release.
  Contract unset update fields now preserve original values; explicit null remains deliberate
  clearing. UI omits protected notes and omits price-only revision description overrides.
- Initial commercial/contract/migration regression 27 passed (38.00s). Initial new review suite
  48 passed / 5 failed (88.68s): deleted-owner test reused an old different request with the same
  key, correctly encountering idempotency conflict before lookup. Correct identical-request replay
  now passes all five targeted cases (8.11s); no permission or business rule was weakened.
  Copy-chain/source-release independence test passed (2.81s). Legacy CRM/export/payment guard
  tests now inspect their exact installed revision in isolated copies, so newer forward guards
  do not mask old guard behavior; all three passed (18.99s), with original fingerprints retained.
- Frontend initially187 (11.76s), expanded192 / 38 files (11.90s), TypeScript/ESLint passed.
  Ruff/format323, mypy204 and generated-client drift passed.
- Full backend collected667: 662 passed / 5 failed (915.41s). Four older order-cost assertions
  expected unreviewed prose to remain public; updated exact DTO assertions now require hidden
  prose and additionally prove stored terms/descriptions unchanged. The old product-index test
  attempted a populated0029 downgrade, correctly refused. It now uses an isolated0023 snapshot,
  verifies safe0022 downgrade/index removal, then head upgrade/index restoration and identical
  historical row fingerprints. Both affected files passed all10 tests (14.41s), with Ruff/format.
  All667 collected cases therefore have passing evidence across the full run and targeted rerun;
  this is not a claim of one subsequent all-green full run. Existing Starlette/httpx warning remains.
- Browser initially13 passed / 1 failed / 14 skipped: its role helper navigated after setting a
  token, so the fixture initialization reset it to Sales. Navigation now precedes the explicit
  role switch. Full rerun28 passed (3.2m), including all five independent source-review journeys.
  All ten375/1440 review screenshots visually inspected: wrapped original text, visible controls
  and no horizontal overflow. Code-simplifier review retained explicit domain locks and the shared
  review form; no broad cross-domain mutation abstraction or business-policy relaxation.
- API/Web/worker/beat production image builds and isolated0029 startup passed; Alembic head and
  clean metadata, worker pong and both Web health endpoints200 verified. Isolated containers
  stopped successfully with all volumes retained; main containers were not restarted/upgraded.
  The shared local API image tag was rebuilt. Whole-V1 remains open, including procurement prose,
  AI history, remaining command/list gaps, real provider login and initialized joint recovery.

## Payment source-text confidentiality checkpoint: 2026-09-06

- 0028 preserves notes with tenant-bound nullable review metadata and populated downgrade refusal.
  Detached projections cover payment reads, creation/allocation durable replay and reversal replay.
  Money/allocations/status remain unchanged; bank references are identifiers, not narrative notes.
  Independent source review requires payment.read plus profit.read, exact version/digest and
  confirmation/reason/key, with a payment-only lock and atomic activity/audit/outbox. Reversal notes
  are independently confidential. User-authorized identifiers must not contain internal costs.
- Shared receipt-card reviewer and optional confidential note recording are implemented. UI keeps
  the existing ledger design; generated API mutations remain authoritative despite generic skill
  guidance recommending Server Actions, which does not override the accepted project architecture.
- Initial payment/finance/migration regression: 29 passed (37.12s). Expanded payment review suite:
  13 passed (18.65s), including role/service/HTTP/replay, concurrent decisions, rollback at all three
  evidence stages, old0027 preservation, stale/restored/deleted content, and reversal independence.
  Frontend initially 185 passed / 38 files (11.58s); after adding two explicit protected-note/
  identifier display cases, 187 passed / 38 files (11.04s). TypeScript/ESLint, Ruff/format312 and
  mypy195 passed. Code-simplifier review retained the existing shared review form and one detached
  payment snapshot path; domain-owned locks/evidence remain explicit, without generic money mutation.
- Full browser 28 passed (2.9m), including receipt recording, operations hidden / manager exact
  review / operations visible, with bank identifiers readable throughout. 375/1440 payment review
  screenshots visually inspected with no horizontal overflow. Generated client drift passed.
- API/Web/worker/beat builds and isolated 0028 startup passed; current head, metadata consistency,
  worker pong and both Web health endpoints 200 verified. Main runtime not restarted/upgraded;
  shared API image tag rebuilt. Isolated containers stopped successfully with all volumes retained.
- Full backend 613 passed (734.88s), with the existing Starlette/httpx deprecation warning;
  terminal exit 0, stable 0028 schema throughout the run. No whole-V1 completion claim; all other
  requirements and identified source/snapshot/AI/auth/recovery gaps remain.

## Export source-text confidentiality checkpoint: 2026-09-06

- 0027 preserves original notes/rejection_reason with nullable tenant-bound review metadata.
  All Export query/create/replay/follow-up/state-command services return protected detached DTOs;
  stored facts, money/date/checklist behavior and business state transitions remain unchanged.
  Case and manual submission receipt numbers remain identifying fields under the user policy,
  with cost/profit entry prohibited. The policy is not automated text detection.
- Independent source-review endpoints require export.read plus profit.read, exact version/hash,
  reason/confirmation/key, live owner and atomic activity/audit/outbox. Final cases may be reviewed,
  not reopened. Revoke replay remains current; mutation and restoration invalidate old release.
  Code-simplifier review uses one typed projection and one explicitly whitelisted decision path
  per domain, with a shared existing frontend form; no cross-domain business mutation abstraction.
- Export/CRM/migration regression 32 passed (38.10s); initial new Export suite 21 passed (29.17s).
  Expanded Export suite 24 passed (68.33s), covering role, service/list/HTTP, rollback, legacy
  preservation/downgrade refusal, concurrent decisions, create replay and follow-up/state writes.
- Frontend 184 passed / 38 files (12.13s). Initial TypeScript found refunds vs refund route-kind
  mismatch; explicit mapping fixed it. Subsequent TypeScript/ESLint passed. Ruff/format 308,
  mypy 193 and generated-client drift passed. Migration SQL line wrap is formatting-only with
  identical SQL. Full backend 597 passed (721.17s), with the existing Starlette/httpx warning.
  The three later-added concurrency/command tests passed within the separate 24-test group;
  they were not collected by this already-running full suite.
- Full browser 28 passed (3.1m), including operations hidden / manager exact source release /
  operations visible after refund finalization, with receipt ID continuously visible. 375/1440
  export-source-review screenshots inspected: no overflow. API/Web/worker/beat builds and isolated
  0027 startup, current head, clean metadata, worker pong and both Web health 200 passed.
  Isolated containers stopped with all volumes retained; main runtime not upgraded or restarted
  (shared local API image tag rebuilt).
- Whole-V1 remains open: other original prose/snapshots, AI history, command/list gaps, real
  provider login, initialized commercial-system recovery and requirement-by-requirement audit.

## OIDC algorithm agreement checkpoint: 2026-09-06

- Live local Logto discovery/JWKS inspected read-only: ES384 / EC / P-384. The API now pins
  OIDC_SIGNING_ALGORITHM to RS256 (unchanged default) or ES384. Unverified headers only compare
  to trusted configuration, never choose policy or JWKS location. Key algorithm/type/curve
  must match; unsigned/HMAC tokens remain forbidden in the runtime adapter. Existing crypto
  dependencies are reused; no new dependency, schema, role or browser contract was introduced.
- Real asymmetric signature tests cover both algorithms, issuer/audience/expiry/subject/org,
  wrong signatures/key IDs, key algorithm confusion, wrong EC curve, unsafe startup settings
  and runtime factory wiring. API integration preserves local membership and tenant gates.
  Initial auth 35 passed; expanded auth/tenant 63 passed; final auth/tenant/member 87 passed
  (37.09s), including test-fixture cleanup refinement. Code-simplifier review kept explicit
  checks with one decode path and did not alter local fixture-auth behavior.
- Ruff, format (303 files), mypy (190), generated-client drift and Compose configuration passed.
  API image built, isolated ES384 override started, runtime setting/factory both verified ES384,
  Web health and platform health returned 200. Test containers stopped, volumes retained.
  Main runtime and Logto accounts were not changed; shared API image tag was rebuilt.
- Reproduce isolated configuration using root + fresh.compose.yml + oidc-es384.compose.yml
  with project trade-fresh-acceptance. This is startup/configuration and generated-key evidence,
  not a real provider-issued token, redirect login, initialized Logto restore or whole V1 pass.
  Full backend 542 / frontend 182 / browser 28 below predate this small auth follow-up; the
  scoped 87-test run is its final regression, not an asserted new full-suite result.

## CRM source-text confidentiality checkpoint: 2026-09-06

- 0026 preserves Lead notes/source and Opportunity lost_reason, with nullable review metadata
  and tenant reviewer constraints. Existing facts default confidential; populated downgrade fails.
  Detached service responses cover reads, creates, transitions, conversion and keyed replays.
  Identifying names remain visible under the user-approved policy.
- Separate source review binds exact fields and row version, requires original read plus profit
  authority, and atomically writes activity/audit/outbox. Shared core review primitives preserve
  Work behavior; source approval does not release historical timeline text.
- Initial CRM/Work/migration 45 passed. Expanded regression 38 passed / 1 failed (56.83s): old
  sales loss-reason assertion corrected to hidden plus a manager assertion of unchanged evidence.
  Frontend now 182 passed / 38 files (13.39s); mypy 190 and generated-client drift passed.
- Expanded CRM source suite 24 passed (35.11s), including live HTTP release and protected lists,
  cross-tenant GET/POST using an active reviewer in both organizations, concurrency, mutation,
  rollback and populated legacy upgrade protection. First expanded run had 22 passed / 2 failed
  because the new foreign fixture membership defaulted to INVITED; explicitly ACTIVE now tests
  resource isolation rather than early membership rejection. No production permissions changed.
- Earlier non-order final full run was invalid: 515 passed / 5 failed (516.86s), because 0026
  was introduced while that process retained pre-0026 model metadata. No acceptance claim uses
  that mixed-version run. Clean stable-schema full backend: 542 passed (700.42s), with the
  existing Starlette/httpx warning. The two additional list/HTTP tests passed in the separately
  reported 24-test CRM suite; they were added after the full run collected tests.
- Full browser 28 passed (2.9m), including sales hidden / manager source review / sales visible.
  375/1440 source-review screenshots were visually inspected with no horizontal overflow.
  First browser attempt hit permissions on old screenshot cleanup and was stopped; authorized
  rerun passed. Frontend typecheck, ESLint, Ruff and formatting passed.
- API/Web/worker/beat images built; isolated startup passed with 0026 head, clean metadata,
  worker pong and both Web health endpoints 200. Containers stopped, volumes preserved; main
  runtime untouched (shared local API image tag rebuilt). Whole-V1 acceptance and the remaining
  text-policy inventory stay open.

## Non-order timeline confidentiality checkpoint in progress: 2026-09-06

- Lead/company/opportunity/customs/refund activity query services now protect summary/details
  before HTTP serialization. Minimal CRM serializers retain their original summary-only shape
  with visibility flags. Stored records remain intact; existing 0025 fields require no migration.
- Explicit whitelisted subject-scoped review checks profit.read and original subject permission,
  active tenant owner and exact activity relationship. Owner-before-record locking, shared
  digest/version decision logic, atomic evidence and current-resource replay retain order review
  guarantees. Final cases remain reviewable; unsupported subjects fail closed. Existing order
  endpoints and durable payload semantics are unchanged.
- Shared Web reviewer uses generated subject types, original permissions, full target/session
  keys and the same RHF/Zod exact-snapshot form. Hidden histories receive a confidentiality label.
  Code-simplifier review retained one decision transaction/form and removed test type casts;
  original domain commands and state transitions are unchanged.
- Initial focused backend 65 passed / 1 failed (72.32s): old export test expected operations to
  read unreviewed details. It now separately asserts manager evidence and operations protection.
  All 38 new timeline tests passed in that run; expanded unauthorized POST/service checks with
  export/opportunity regression passed 52 tests (85.79s). Initial full backend 516 passed / 1
  failed (622.73s), solely the old opportunity summary assertion. That assertion now retains
  sales redaction plus manager historical evidence, without changing business checks; the
  successful 52-test group includes this repair. Second full backend: 516 passed / 1 failed
  (541.56s). Expense reversal concurrency itself passed, but the historical-copy helper inserted
  a reversal before its original when random UUID order placed it first. The helper now orders
  self-referencing rows by their composite FK dependencies, without nulling references, disabling
  constraints or changing source facts. Cyclic/missing dependencies fail explicitly. Three new
  deterministic helper tests (including real PostgreSQL FK insertion) plus the affected expense
  test passed: 4 passed (5.36s). Final full rerun follows this repair.
- Frontend initial full 174 passed / 38 files (47.67s); expanded review form 9 passed (2.06s).
  Final full frontend 180 passed / 38 files (15.38s). TypeScript (incremental disabled after cache EPERM), Ruff,
  format, mypy 186, scoped ESLint and generated-client drift passed.
- Full browser 28 passed (3.1m), including company history live operations/manager release.
  375/1440 company-text-review screenshots in apps/web/test-results were visually inspected;
  no horizontal page overflow. API/Web/worker/beat builds and isolated startup passed, 0025
  head, clean metadata, worker pong and both Web health endpoints 200. Isolated containers
  stopped with all volumes retained; no main runtime upgrade/restart (shared API tag rebuilt).
- This does not release standalone source notes/references, complete AI text policy or certify
  whole V1. Real login, initialized full-system restore and remaining guide obligations stay open.

## Order Work confidentiality checkpoint: 2026-09-06

- 0025 adds nullable reviewer/time/release digests to tasks and activities without rewriting
  historical bodies. Order task/activity query services and completion/DONE replay protect
  arbitrary text/JSON via detached DTOs. Type/status/date remain visible; low-role titles and
  summaries are null, details empty, never a fabricated business value.
- Order-scoped review commands bind exact text/details and resulting record version, require
  cost authority plus original read permissions, confirmation/reason/key, preserve lock ordering
  and atomically write evidence. A later mutation invalidates release even after text restoration.
- Initial Work + migration group 24 passed (25.40s). Legacy Work/document migration group 2
  passed (2.76s). Expanded Work group 23 passed (42.73s), adding competing decisions and explicit
  unauthorized HTTP/service write checks. Initial full backend: 469 passed / 8 failed (635.56s).
  All eight were old migration tests attempting a downgrade through the new populated Work
  guard. The guard remains intact: tests now allocate independent old-schema databases, copy
  only that schema's fixture columns with FK checks enabled, upgrade and compare every copied
  row/column. Legacy domain downgrade guards are exercised at their actual historical revisions.
  The source fixture stays read-only; this is synthetic migration evidence, not a production
  backup restore. All eight affected tests passed (30.76s); final full backend 479 passed
  (482.17s), with one existing Starlette/httpx warning.
- Frontend 174 passed / 38 files (12.11s); after pending refresh/collapse guards, finance group
  15 passed (4.34s). TypeScript, mypy 184, generated-client drift and scoped ESLint passed.
  Text review uses existing ledger/form styles; 375/1440 screenshots inspected in
  apps/web/test-results/work-review-*.png. Initial browser: 27 passed / 1 failed (2.9m); the old
  outbox test failed because its fixture path depended on cwd. Source-relative lookup fixed it;
  final full browser 28 passed (2.9m), including manager release and live operations disclosure.
- API/Web/worker/beat images built; isolated startup and migration 0025 head passed, metadata
  check clean and Worker pong; both Web health endpoints returned 200. Isolated containers
  stopped with all volumes retained. Main environment is not upgraded; the shared local API
  image tag was rebuilt. Wider text policy and whole-V1 acceptance remain open.

## Document confidentiality checkpoint: 2026-09-06

- Follow-up race coverage: simultaneous release/restrict with the same opening version yields
  one success/one conflict and one evidence set. Actual manager-to-sales membership downgrade
  rejects review inspection, new decisions and old keyed replay; confidential metadata/download
  remain protected. These tests passed with the original 11 review tests: 13 passed (15.75s).
- A signing-time revoke regression initially reproduced an issued URL after restriction.
  Download now resolves a detached pointer, signs outside the DB session, then rechecks the
  exact selected version, release, content and target permissions before returning the URL.
  Shared pointer validation avoids duplicating authorization logic (code-simplifier review).
  Tests also change privileged title/storage pointer during signing and assert no checked-out
  connection in the storage callback. Final review suite: 16 passed (19.29s); earlier review,
  real storage/version and upload-recovery group: 28 passed (32.98s). Ruff and mypy 182 passed.
  This follow-up changes no schema, frontend or API shape. Final full backend: 455 passed
  (453.52s), one existing Starlette/httpx warning. This precedes the Work slice above.
  Updated API/worker/beat images built and isolated startup passed; migration 0024 head,
  Alembic check clean, Worker pong and both Web health endpoints 200. A first relative-path
  Alembic invocation failed to locate the executable; the absolute runtime path above passed.
  Isolated containers are stopped, volumes retained; shared local API image rebuilt but no main
  runtime restart/upgrade. Prior browser 28/28 is before this backend-only signing recheck.

- Added 0024 nullable release digest/reviewer/time with tenant membership FK and consistency
  constraint. No historical rewrite or automatic release. Review/restrict requires cost authority,
  exact file/content/version, confirmation/reason and idempotency; activity/audit/outbox are atomic.
- Query/create/replacement/complete/resume now return detached document DTO aggregates. Hidden
  metadata is null, not copied into low-role output. Exact-version download requires privilege
  or valid release; business-target permission checks share a document-owned access module.
- Review UI is integrated into shipment, contract and export evidence. Existing visual tokens,
  RHF/Zod, scoped query state, durable in-form retries and explicit disclosure are preserved.
  New review/history focused frontend 5 passed; full frontend 171 passed / 37 files. After a
  success-notice persistence fix, document-focused 16 passed. TypeScript and scoped ESLint passed.
- Backend review + upload recovery + migration suite: 27 passed (34.85s), including six roles,
  rollback at each evidence boundary, release/revoke/replay and unchanged stored text. Initial
  upload recovery had 3 fixture failures because service DTOs no longer expose object keys;
  tests now read persisted storage facts separately and all 24 review/recovery tests passed.
- Initial full backend: 437 passed / 12 failed (485.78s). Ten failures traced to an unconditional
  downgrade guard blocking unrelated old migrations even in document-empty databases. 0024 now
  permits downgrade only when document_versions is empty; any existing document prevents loss
  of confidentiality, including unreviewed legacy evidence. A populated 0023-to-0024 test proves
  unchanged name/checksum, null review facts and refused downgrade. Real MinIO replacement tests
  now explicitly review each verified version as manager before operations downloads it. Foreign
  target lookup asserts 404 instead of the former empty 200. Focused affected suite: 16 passed.
  Final full backend rerun: 450 passed (503.94s), with one existing Starlette/httpx
  deprecation warning. Two later low-role upload metadata assertions separately passed in
  the 13-test upload recovery suite (17.73s); no production change followed that full run.
  First browser run: 13 passed / 1 failed / 14 not run (3.8m), waiting on an old filename-based
  resume form locator. Restricted names now have an explicit label and a version-ID locator.
  Primary browser flow includes manager release before operations file use.
  That rerun passed 28/28 (2.7m); 375px/1440px review-form screenshots inspected. API/worker/beat/
  Web images built, isolated 0024 startup passed, Alembic check clean, Worker pong and both Web
  health endpoints returned 200. Isolated containers stopped with volumes preserved; the shared
  local API image tag was rebuilt, but the main environment was not started or upgraded.
  Document browser workflow, real versioned-storage review/download and isolated runtime
  builds/startup are verified above. Wider historical free-text enforcement remains pending;
  this checkpoint is not full-policy or V1 acceptance. No production or main-runtime upgrade
  has been performed.

## Restricted quotation checkpoint: 2026-09-06

- Shared quotation_projections now applies profit.read inside list/detail and resource-returning
  command services, including revision/approval/acceptance replay. Routers return detached DTOs;
  protected version/item/list fields are nullable and stored snapshots remain unchanged.
- Create validates a copy with unset inputs preserved. Create/revise reject protected cost
  fields (including explicit nulls) without profit.read before replay. Sales can create matching-
  currency drafts from Product costs and revise source-bound lines without resending costs.
  Missing cross-currency rates or changed currency with unresolved inherited rate return
  COST_PREPARATION_REQUIRED. No fake one-rate or zero-cost replacement; no migration needed.
- Web hides cost/profit columns and charts by permission, omits protected sales creation inputs,
  leaves authorized rate inputs blank for explicit preparation, and sends only source IDs and
  selling values from price-only revision. Null privileged amounts show unavailable. Code
  simplification review centralizes response policy and removes duplicate router serialization;
  unrelated state/transaction/financial rules are unchanged.
- New policy tests: 14 passed (24.17s), covering six roles, service/HTTP reads, protected-input
  rejection, safe creation/revision, command outputs/replays and unresolved currency changes.
  Existing quotation/revision/validity/numbering/order focused suite: 44 passed (43.62s).
- First full backend: 432 passed, 3 failed (508.18s). Old snapshot comparisons used sales costs
  and an old explicit-cost override was sent by sales. Tests now retain sales revision but read
  privileged snapshots as manager; explicit cost maintenance uses manager with an explicit FX
  rate. All 6 snapshot tests passed (9.17s). Final full backend rerun passed 437 tests
  (3584.96s), with one existing Starlette/httpx deprecation warning.
  A separately added saved-PROFIT-run permission-revocation regression passed (1 test, 3.87s)
  and Ruff passed; this new test was not included in the 437-test run.
- Frontend full: 168 passed / 36 files; TypeScript, Ruff/format, mypy 179 and generated-client
  drift passed. Scoped ESLint passed. Browser initial: 25 passed / 1 order-width failure
  (401px content at 375px). Added overflow diagnostics without changing assertions or hiding
  content; expanded rerun passed 27/27 in 2.4m, including actual quote role-switch responses.
  Reviewed sales 375px and manager 1440px quotation screenshots. A final browser rerun adds
  narrow table-scroll amount screenshots. That run failed after abnormal 51.2m elapsed time;
  the subsequent run again failed order width (25 passed, 1 failed, 1 not run, 2.5m).
  Therefore the earlier green run does not close the intermittent width defect. Diagnostics
  now exclude descendants of horizontal clipping/scrolling containers and include element
  bounds. A further text-range diagnostic identified finance timeline event names such as
  supplier_payment_allocation.reversed overflowing their text boxes (not the order table).
  Scoped overflow-wrap:anywhere on timeline entries fixes the cause without clipping content.
  Added a deterministic narrow-container long-text regression and awaited loaded timeline facts
  in the role test. Final browser: 28 passed (2.5m), including quote/order role switches and
  mobile table-scroll amount screenshots. TypeScript and scoped ESLint passed. Code-simplifier
  review retained a single scoped CSS rule and explicit diagnostics, without unrelated refactors.
  Updated Web production container build/start and both health endpoints passed; stopped the
  isolated environment with volumes retained. No main-environment changes.
- Isolated API/worker/beat/Web builds, config, startup, 0023 head, clean Alembic metadata,
  worker pong and both Web health HTTP 200 passed. Stopped isolated containers, volumes retained;
  main runtime untouched (shared local API image tag rebuilt).
- Next: finish final runs/screenshots and review wider timelines, tasks, AI historical outputs
  and arbitrary document/free-text confidentiality. WorkQueryService.order_activities still
  returns full Activity facts with only ORDER_READ; inspect cost-bearing events before closing
  ADR-020. Legacy command idempotency/cursors, real Logto, full restore, real AI and production
  choices remain open. This checkpoint is not V1 acceptance.

## Restricted procurement checkpoint: 2026-09-06

- ADR-020 procurement query/command/replay services now return detached protected DTOs;
  low roles receive null currency/rate, original/converted/retained amounts and line costs.
  Quantities, dates and statuses remain available; no stored snapshot is rewritten.
- Create/approve/cancel/amend require profit.read plus their existing domain permissions.
  OPERATIONS retains send/confirm/receive/close but no procurement.approve. FINANCE does not
  gain procurement authoring. History hides arbitrary summaries/reasons and retains only
  allowlisted operational command metadata; broader free-text/document review remains open.
- Web pricing controls/cards/commitment totals and supplier-finance entry require cost authority.
  Missing values are not zero; protected purchase histories have readable Chinese event labels.
  Code-simplifier review kept the shared projection and exact decimal aggregation; no unrelated
  refactor. UI checks preserve existing ledger styling, labels and narrow-screen layout.
- Existing focused procurement/order tests: 33 passed. New cost-policy tests: final 8 passed
  (11.81s), including six roles, service boundaries, cross-tenant access, unchanged ORM/evidence,
  quantity-command replay and manager-to-operations downgrade with the existing token.
  Earlier 7-case run had one expired-token 401 after an abnormal 42-minute delay; ordinary
  rerun passed all 7 without weakening token verification. First full backend: 393 passed,
  29 failed (439.94s), all from the shared supplier-settlement fixture still creating priced
  purchases as operations. Its creator is now manager; final full rerun: 423 passed,
  one existing Starlette deprecation warning, 389.20s. No financial assertions were removed.
- Frontend final full: 168 passed / 36 files; orders scope 27 passed / 4 files.
  Browser full: 26 passed in 2.9m, including manager pricing and
  operations fulfillment, actual list/detail redaction for manager/sales/operations, and
  preserved quantities. Reviewed 375/1440 procurement screenshots; no page overflow.
- Ruff format/check, mypy 178 files, TypeScript, generated-client drift and scoped ESLint
  passed. The new test import-order warning was corrected and checks rerun successfully.
  Isolated API/worker/beat/Web builds and config passed, 0023 head and
  clean metadata verified, worker pong and both Web health endpoints returned HTTP 200.
  Isolated containers stopped with all volumes retained; main runtime unchanged. Shared API
  local image tag was rebuilt. All runs listed in this checkpoint are terminal.
- This checkpoint does not close quotation safe drafting, other timelines/AI historical outputs,
  arbitrary references/descriptions or binaries, real Logto login, initialized full-system restore,
  real-model quality or production deployment choices. It is not V1 acceptance.

## Restricted sales-order snapshot checkpoint: 2026-09-06

- ADR-020 order enforcement now lives in shared order_projections called by query, create,
  confirm and completion application services, including existing-resource/repeated commands.
  Services return detached DTOs, not unrestricted ORM tuples. Without profit.read, order cost,
  profit/margin and six protected item fields are null; selling prices, quantities, taxes/freight,
  total and agreed deposit remain intact. Underlying cached/committed facts are not modified.
  No migration or new command permissions; original lock/evidence/financial rules are preserved.
- HTTP routers return service projections directly, including the finance completion route.
  Code-simplifier review kept one explicit shared field policy and removed duplicate unrestricted
  router assembly. Internal repositories continue to support exact authorized calculations.
- Web order lines hide cost/profit columns by permission and explain restricted access. Null
  values never format as zero or become a zero purchase-input default. Existing narrow-screen
  table scroll is retained inside its region; actual selling fields remain available.
- New backend role/service tests: 7 passed. Order/procurement/list/numbering/finance regression:
  33 passed before expanded completion assertions; role+final completion/finance tests: 21 passed.
  Full backend initial run: 413 passed, 2 failed (465.89s), both old snapshot tests expected sales
  to read costs. They now keep sales creation and assert redaction, then use manager reads to
  prove complete historical snapshot invariance. All 6 snapshot tests passed after correction.
  Final full backend rerun: 415 passed, one existing Starlette deprecation warning, 398.41s.
  That run predates procurement enforcement and is evidence for this order checkpoint only.
- Frontend full: 165 passed / 36 files. Final changed order file: 12 passed. Full browser:
  26 passed in 2.4m after additional detail-page width and table-scroll screenshots (earlier run
  26 passed in 2.5m). Actual GET cost fields tested across manager/sales/operations in-place
  switches; 375/1440 screenshots inspected, including narrow-screen selling/cost columns after
  scrolling. No whole-page horizontal overflow. This is not procurement-card confidentiality.
- Ruff/check/format, mypy 177 files, TypeScript, scoped ESLint, Prettier and generated-client
  drift passed. Initial Web production build caught unsupported exact options in two Testing
  Library calls; anchored-name matching fixed the tests, then typecheck and Web build passed.
- Isolated API/Worker/beat/Web images built; config/start/0023 head/clean Alembic metadata,
  Worker pong, Web health and platform-health HTTP 200 passed. Initial manual Worker probe used
  the wrong module name; corrected to configured worker.app and passed. Containers stopped with
  volumes retained; running main environment unchanged (shared API local image tag rebuilt).
- Quotation costs/overrides and procurement pricing/cards/commitment strip/history remain open,
  as do remaining timeline/free-text/documents and AI confidentiality review, real Logto login,
  initialized full-system restore and production choices. This checkpoint is not V1 acceptance.

## Restricted catalog cost checkpoint: 2026-09-06

- ADR-020 records the user's explicit restriction of both cost and profit to ADMIN/MANAGER/
  FINANCE. Product services redact cost/currency in detached DTOs without changing ORM facts.
  Cost-bearing product creation and supplier-reference reads/history/writes/replay require
  profit.read at both API and application-service boundaries. SALES/OPERATIONS retain basic
  product browsing; FINANCE receives no new authoring permissions. No migration is required.
- Web separates basic product details from supplier pricing and never mounts supplier queries
  for unprivileged roles. Preparation hands product creation to manager/admin. Browser checks
  switch manager to SALES and OPERATIONS, verify null actual product-response costs and direct
  supplier API 403, and capture reviewed 375/1440 layouts without overflow or price controls.
- Catalog-focused backend: 31 passed. Full frontend: 162 passed / 36 files. Full browser:
  25 passed in 2.2m. The first browser attempt failed because the test did not reopen preparation
  after a role-switch remount; the corrected sequence preserves session isolation and passes.
- Initial full backend: 407 passed, one failed because the foreign-organization fixture used
  SALES to create a cost-bearing product. The fixture now uses a separate foreign MANAGER only
  for product setup and retains SALES for other actions; all six snapshot tests passed afterward.
  Final full backend rerun: 408 passed in 360.07s, exit 0, one existing Starlette deprecation
  warning. This supersedes the initial failed run, not the remaining policy implementation gaps.
- Ruff check/format, mypy (176 source files), TypeScript, scoped ESLint, changed-file Prettier
  and generated-client drift passed. Code-simplifier review removed redundant grant-then-remove
  entries from SALES/OPERATIONS permission sets without changing effective permissions.
- Isolated API/Worker/beat/Web builds and runtime checks passed at migration 0023, with no new
  upgrade operations, Worker pong and Web HTTP 200. Isolated containers stopped, volumes retained;
  running main containers were not restarted or upgraded. Shared local image tag was rebuilt.
- This is catalog-only enforcement. Quotation/order read and command/replay projections, safe
  sales snapshot inputs, priced procurement restrictions, timeline/AI and document confidentiality
  remain open. Real Logto login, full initialized-system restore and production choices remain
  separate overall acceptance gaps.

## Persisted pending-upload recovery checkpoint: 2026-09-06

- Added the explicit document/version upload-session endpoint. Original filename, MIME, size
  and SHA-256 are required and matched to PostgreSQL metadata. Organization/document/version
  relationship and document-write/target-read checks precede signing; finality/current-version
  checks run again after signing. Accepted recovery returns no PUT URL. No new version, key,
  audit/activity/outbox or migration is created by read-only resumption; completion retains
  existing atomic evidence and immutable storage pinning.
- Shipment, contract and customs/refund lists offer a shared RHF/Zod original-file control for
  writable current pending versions. Session changes remount it; pending disables duplicate
  submission, errors are field-linked, and successful recovery refreshes owner queries.
  No browser credential/URL persistence is added. Code-simplifier review extracted common
  checksum and PUT/complete operations instead of duplicating the transfer protocol.
- Full backend: 401 passed in 452.55s, one existing Starlette deprecation warning. Upload
  recovery subset: 13 passed; full frontend: 161 passed / 36 files. Ruff/check/format, strict
  Python/TypeScript, scoped ESLint, formatting and generated-client drift passed.
- Final full browser: 25 passed in 2.3m. Owner fault steps now cover lost creation response,
  page reload, rejected wrong file, lost re-sign response, and successful existing-version
  continuation; IDs/version numbers stay fixed with one creation and completion. Existing
  shipment open-form completion-response-loss test remains. First attempt: 12 passed, primary
  timed out, 12 unrun because fixture init reset manager to SALES at reload and correctly hid
  the write control. Test helper restores its starting fixture role; no application permission
  or timeout relaxation. Both 375/1440 screenshots were captured, mobile/desktop control
  screenshots reviewed; responsive overflow assertions passed for every resumed owner.
- API/Worker/beat/Web container builds and isolated startup/config passed. Alembic 0023,
  clean metadata, Worker pong and Web HTTP 200 verified. Isolated containers stopped with
  volumes retained; main runtime untouched. No real-login, live-AI or production claim.
- Persisted pending-file recovery is closed for these owners. Remaining V1 audit includes
  legacy command guards and bounded lists; cost/profit field policy still requires the user's
  decision. Real Logto setup, commercial-fixture/initialized-identity restoration and live
  provider acceptance remain unverified. This checkpoint is not complete V1 acceptance.

## Upload-owner fault acceptance checkpoint: 2026-09-06

- Added actual browser fault cycles for contract evidence, shipment replacement, both customs
  documents and both refund documents. Each commits upload-session creation then aborts its
  response, commits completion then aborts that response, and submits again. Assertions prove
  three requests retain the same key, exact payload, document ID and version ID, with exactly
  one completion and no PUT URL on accepted recovery. Replacement remains version 2; new
  evidence remains version 1. Existing shipment creation-upload fault coverage remains intact.
- A shared test helper keeps these owner-specific steps consistent (code-simplifier review).
  Initial expanded journey failed because the unscoped export alert locator also matched the
  Next.js route announcer, after contract/replacement had already passed. Scoped the locator
  to the actual upload error; no application behavior or timeout was weakened.
- Final full browser: 25 passed in 2.1m. TypeScript, scoped ESLint and test-source formatting
  passed. This turn changed only browser tests and acceptance notes: no new runtime build,
  backend/unit suite, migration or main-environment deployment is claimed.
- This closes the named independent owner fault-path evidence gap, not cross-reload recovery.
  Current DB metadata can support guarded existing-version recovery with explicit exact file
  re-selection; the public resume operation and shared UI still need implementation/acceptance.
  Full V1 and the unresolved sensitive-field, real-auth/provider and full-restore items remain.

## Open-form upload response recovery checkpoint: 2026-09-06

- Upload/create-version endpoints accept optional durable keys, validated metadata/target/opening
  version hashes and atomic document/version/link/evidence/key writes. Identical replay recovers
  the original version; changed input conflicts. Legacy omission remains a new allocation.
  Pending recovery reauthorizes target, refuses finalized/superseded records and rechecks after
  external signing. Accepted replay returns upload_url=null without new PUT signing; accepted
  facts can be recovered after target finalization. Pinned storage/scanning rules are unchanged.
- Shipment, contract and export upload hooks use a shared session-scoped attempt holder and
  captured clients. Session/PUT/complete failures retain a key for an unchanged fingerprint;
  changed payloads rotate it, success clears it, session changes isolate old in-flight holders.
  Code-simplifier review moved ref access into the event callback, avoiding render-time mutation
  and the nonsemantic useMemo cache for retry identity. Generated client includes nullable URL.
- Backend full suite: 394 passed, one existing Starlette warning, 4944.66s wall time during an
  abnormal elapsed-time interval. Two more boundary cases were subsequently added; final
  recovery-specific suite: 8 passed in 11.78s. It covers replay/conflict, replacements, all three
  evidence rollback points, concurrency, HTTP keys, foreign IDs, permission/finality and a
  completion occurring during signing. No claim of a full 396-test rerun is made here.
- Final frontend: 156 passed / 35 files in 10.20s. Strict Python/TypeScript, Ruff/formatting,
  scoped ESLint and generated-client drift checks passed. First browser run ended with expired
  test credentials after a 1.3h elapsed interval (8 passed, 5 failed, 12 unrun); no production
  authentication bypass or token-lifetime change was used. Fresh full browser: 25 passed in
  2.2m. Final fixed-source primary journey: 1 passed in 1.6m. It commits session creation then
  loses its response, commits completion then loses that response, and proves three attempts
  retain one document/key with no second completion after recovery.
- API/Worker/beat/Web builds and isolated config/start passed; final hook changes received an
  additional Web rebuild/start. Alembic remains 20260906_0023, metadata clean, Worker pong,
  final Web HTTP 200. Isolated containers stopped with volumes retained; main unchanged.
- Not yet complete upload recovery: memory-only attempt identity does not survive refresh,
  navigation or closing a form. Need a safe persisted pending-version recovery UI with exact
  reselected-file verification, and independent fault-path browser evidence for contract/export
  and replacement flows. Their ordinary upload journeys pass through the shared implementation.
  Full V1, cost policy, real auth/provider and complete backup recovery remain unaccepted.

## Batched shipment reads checkpoint: 2026-09-06

- Reproduced 13 business SELECTs for six shipments. The list now batches active items and
  current document types: three SELECTs for populated pages and one for empty pages. Item
  creation-time/ID ordering, exact serialized snapshots and page-local count are preserved.
- Detail/command checklist calls share the batched evaluator; organization joins, latest-version
  selection, AVAILABLE status, immutable storage pointers and all soft-deletion filters remain.
  No status/quantity/permission changes, new dependency, migration or API contract changes.
- Ten new tests cover page sizes, empty organization, denied service permission, deleted
  shipments/items, unchanged evidence counts, foreign IDs with valid evidence and rejection of
  deleted document/link/version, pending, unpinned/empty/null pointers, old versions and wrong
  target type. Initial query-budget test failed 13 versus 3 before the fix; targeted suite passed.
- Full API/Worker: 388 passed in 407.58s with one existing Starlette deprecation warning.
  Frontend: 150 passed / 33 files in 9.96s. Full browser: 25 passed in 2.3m. Ruff lint/format,
  strict Python/TypeScript and generated-client drift checks passed. Code-simplifier review
  kept one shared file-eligibility evaluator rather than separate list/command rules.
- API/Worker/beat/Web build and isolated config/start passed. Alembic 20260906_0023, metadata
  clean, Worker pong and Web HTTP 200. Isolated containers stopped with volumes retained;
  main containers not restarted. No visual UI redesign was made or separately claimed.
- Remaining: cursor navigation, upload uncertain-completion recovery across shipment/contract/
  export, remaining creation/command guards, sensitive-field policy and real auth/provider/full
  recovery acceptance. This checkpoint does not certify all V1 requirements.

## Atomic quotation/order numbering checkpoint: 2026-09-06

- Reproduced concurrent first-number failures in both legacy select/insert allocators on
  distinct commercial aggregates. Both now delegate to the existing PostgreSQL atomic upsert
  helper inside the business transaction. Q/SO formats, UTC year partition, permissions and
  historical facts are unchanged; no migration, dependency or API contract change is needed.
- Fifteen new tests cover distinct concurrent creations, organization/type/year isolation and
  separate activity/audit/outbox rollback for absent and existing sequence rows. The quotation
  evidence expectation explicitly includes CRM stage transitions. Targeted suite: 15 passed.
- Full API/Worker: 378 passed in 389.32s, one existing Starlette deprecation warning.
  Frontend: 150 passed / 33 files in 9.75s. Full browser: 25 passed in 2.2m.
  Ruff lint/format, strict Python/TypeScript and generated-client drift checks passed.
  Code-simplifier review retained thin allocator delegates and explicit expected count deltas.
- API/Worker/beat/Web builds and isolated Compose config/start passed. Migration remains
  20260906_0023, metadata clean, Worker pong, Web HTTP 200. Isolated containers stopped with
  volumes retained. Shared local API image tag rebuilt; main containers were not restarted.
- This closes the confirmed quotation/order first-number race, not full V1 acceptance.
  Shipment list batching, shared upload recovery, remaining retry/navigation audit, sensitive
  field policy, real Logto/AI and full recovery evidence remain open. The cost-access policy
  question was presented again; no role policy was silently selected.

## Complete quotation revision snapshots checkpoint: 2026-09-06

- Reproduced catalog drift before the fix: copied revision SKU/unit changed with Product;
  sourced line defaults and archived-product copying also failed the new acceptance tests.
  Revision now accepts source_item_id on revision-only inputs and resolves it exclusively from
  the locked current version in this organization. Product mismatch returns 409; foreign,
  unrelated and older-version source IDs return 404 without partial facts.
- Omitted items copies all current lines. Explicit sourced lines preserve SKU/unit and inherit
  omitted commercial inputs, with explicitly supplied price/quantity/cost/description overrides.
  New unsourced lines use active Product defaults; archived products may be copied from existing
  facts but cannot be added as new lines. Typed backend defaults and one snapshot-copy helper
  keep the two paths explicit. Audit records source line mappings in the same transaction.
  No historical rows are rewritten, and no schema migration or dependency change is required.
- Six new snapshot tests cover catalog drift, reordering, full accepted-order propagation,
  archived copies/new-line rejection, explicit zero overrides, audit mapping, retained originals,
  actual foreign-organization source rejection and stale source rejection. Combined with revision
  replay tests: 14 passed. Full backend/Worker: 363 passed, one existing Starlette warning, 362.94s.
- Final frontend: 150 passed / 33 files, 9.51s. Browser submits exact source IDs even for duplicate
  product rows; full browser 25 passed in 2.3m, including lost-response replay and end-to-end
  settlement/refund. Strict Python/TypeScript, Ruff, scoped ESLint, formatting and regenerated
  OpenAPI/client drift checks passed. There was no visual redesign in this payload-only UI change.
- API/Worker/beat/Web production builds and isolated startup/config passed. Head remains 0023;
  Alembic metadata clean, Worker pong and Web HTTP 200. Isolated containers stopped with volumes
  retained. Shared local API image tag rebuilt, but main containers were not restarted.
- Full V1 remains unaccepted: sensitive response policy, remaining command/numbering audit,
  shared upload recovery, real Logto/AI and complete recovery evidence remain open.

## Guarded quotation revision and session recovery checkpoint: 2026-09-06

- Revision supports expected_version_id and Idempotency-Key, with tenant-scoped durable hashing,
  original generated-version replay, changed-payload conflict and stale-editor rejection. Version,
  items, activity, audit/outbox and completed key commit together. Caller input is not mutated;
  audit before-data preserves the real previous status. Existing key/version tables need no migration.
- Replays return the original version's current state, not necessarily the current quotation
  version. Permission checks precede replay. Three independent evidence failures roll back the
  entire change and key; concurrent identical, changed-payload and competing-key requests prove
  exactly one new version. Optional guard omission deliberately retains legacy current-version
  behavior and is not equivalent to guarded retry. No API-breaking contract was silently imposed.
- Web always supplies both guards, preserves opening snapshot across refetches, uses stable
  unchanged-payload keys and a synchronous in-flight guard. Changed payloads rotate keys. Session
  changes remount editors and scope quotation/detail query caches. Closing/reopening loses retry
  identity and explicitly requires checking the ledger first; no automatic retry is introduced.
- Backend/Worker full: 357 passed, one existing Starlette warning, 374.11s. Specialized revision
  suite: 8 passed. Final frontend: 150 passed / 33 files, 12.37s; Python/TypeScript strict checks,
  scoped ESLint, Ruff/formatting and generated client drift passed. Initial new audit test used
  the ORM column label instead of before_data; corrected before final regression.
- Full browser: 25 passed in 2.5m, including server-commit/response-loss then same-key retry:
  exactly two versions remain and returned current ID equals the first committed revision ID.
  The complete deposit/procurement/documents/delivery/balance/refund journey remains green.
- API/Worker/beat/Web production builds and isolated startup/config passed. Alembic head 0023,
  clean metadata, Worker pong and Web HTTP 200 verified. Isolated containers stopped and volumes
  retained; main containers not restarted. The shared local API image tag was rebuilt, not the
  running main deployment. A final session-isolation test was added after builds; local strict
  typing and full frontend tests were rerun; application source stayed fixed during verification.
- Still open: complete SKU/unit revision snapshot copying, omitted-guard legacy policy,
  sensitive-response policy, shared upload recovery, real Logto/AI and full recovery acceptance.
  This is not a complete V1 release certificate.

## Remaining quotation forms and entry gates checkpoint: 2026-09-06

- Create quotation, product/inquiry preparation and isolated-test connection now use RHF/Zod.
  Creation uses stable field-array IDs, exact decimal strings, valid UUID/date/currency fields,
  1–100 lines, default-cost null mapping and retained failed input. Add/remove/cancel and fields
  are pending-protected. Extracted create panel and typed field definitions replace repetitive
  handlers without changing commercial API payloads. Product/inquiry inputs preserve API bounds.
- Entry buttons and mounted forms require quotation.write/product.write/inquiry.write separately;
  changing session remounts the create/preparation editors. No role grants or sensitive-response
  policy changed. Invalid test connection writes no localStorage credentials.
- Final frontend 149 passed / 33 files in 9.13s; strict TypeScript, scoped ESLint, formatting and
  generated-client drift passed. Full browser 25 passed in 2.0m, including creating products,
  inquiry and multi-line quotation, revision, role-switched approval and complete settlement.
  Existing 375px quotation workspace screenshot reviewed; this is not new form screenshot QA.
- Production Web build, isolated startup/config, Alembic metadata check, Worker pong and Web
  HTTP 200 passed. Only isolated containers stopped, with volumes retained; main unchanged.
  Backend/migration unchanged and the historical 349 backend tests were not rerun.
- Creation/revision/inquiry still need an explicit durable uncertain-result recovery audit;
  pending protection and input retention are not idempotency. Sensitive response policy, legacy
  list navigation, shared upload recovery, real Logto/AI and full recovery remain open.

## Quotation revision form and detail permissions checkpoint: 2026-09-06

- Revision uses RHF/Zod with exact nonnegative four-place prices, positive eight-place rates,
  calendar validation, field errors/focus, pending protection and retained failed input. The
  editor is keyed to the current version. Existing immutable cost/quantity snapshots are copied
  unchanged. Detail commands now require their matching API permission; unknown/read-only
  contexts expose no detail writes. Sensitive response policy is not changed by these controls.
- Full frontend 145 passed / 32 files; strict TypeScript, scoped ESLint, formatting and generated
  client drift passed. Full browser 25 passed in 2.1m. Test role changes explicitly notify the
  session store before manager approval and returning to sales. Earlier permission-map/test
  parameter typing failures were corrected before the final successful build.
- Web production build, isolated startup/config, clean Alembic metadata, Worker pong and HTTP
  200 passed. Main environment untouched; isolated containers stopped with volumes retained.
  Backend/schema unchanged; previous 349 backend tests were not rerun for this UI change.
- Revision POST still lacks durable retry/version preconditions. The form explicitly warns to
  inspect versions after uncertain submission; retained values are not safe automatic replay.
  Create/preparation/connection forms and their controls, sensitive-field policy and the other
  remaining acceptance items stay open. No claim of full V1 acceptance or new visual QA.

## Shipment upload and test connection form checkpoint: 2026-09-06

- Upload/replacement and isolated-test connection now use RHF/Zod. File validation rejects
  missing/empty files and sizes greater than 25 MiB before creating a server session. The exact
  25 MiB boundary is covered. Field-linked errors and first-invalid focus provide recovery;
  pending controls remain disabled. Actual upload still uses the existing shared checksum,
  presigned PUT and complete flow. Server scanning remains authoritative for availability.
- Successful upload clears the native file input, form and replacement mode. Failure retains
  file selection. Replacement pins document ID/version as before; cancelling restores the
  default document type. The shared transfer was not modified and is not resumable: rerunning
  it allocates another session. Safe uncertain-completion recovery remains explicit unfinished work.
- Invalid organization UUID/blank test credential does not store either value. This converts
  the isolated-test form only; no real Logto identity, role grant or production auth was created.
- Final frontend: 128 passed / 31 files in 9.17s; strict TypeScript, scoped ESLint, formatting
  and client drift passed. An initial test exposed label-name changes when the inline file
  error appeared; the input now has a stable matching accessible label and error description.
- Full browser: 25 passed in 2.3m, exit 0. The primary journey uploads commercial invoice and
  packing list, creates invoice V2, downloads V1 with original bytes and completes delivery and
  settlement. Latest document-history 375/1440 screenshots were reviewed: upload controls and
  retained versions fit the layout. This is fixture authentication, not actual Logto login.
- Web production build and isolated Compose startup/configuration passed; metadata check is
  clean, Worker pong and Web health HTTP 200. Isolated containers stopped with volumes retained;
  main environment untouched. Backend/migration unchanged; the earlier 349-test backend result
  is historical evidence, not rerun for this UI-only change. No new dependency or ADR required.
- Quotation legacy forms, bounded navigation, sensitive-field policy, upload-session recovery,
  real Logto and complete recovery remain open; this checkpoint is not complete V1 acceptance.

## Shipment create form standard checkpoint: 2026-09-06

- Creation now uses RHF/Zod for fields and selected-line state, removing the separate selection
  state and FormData extraction. Optional UUID/date validation, positive exact quantities with
  14 integer/4 decimal digits, 1–200 selected lines, field-linked errors and invalid-input focus
  preserve backend authority. No float conversion, API/schema change or role change.
- Unselected invalid quantities are excluded from validation and actual payloads; that behavior
  has both schema and DOM-level tests. Retained-form retry still reuses the existing ref-held
  key and changed payloads rotate it. Existing lost-response browser acceptance remains intact.
- Final frontend: 125 passed across 31 files in 10.75s; TypeScript, scoped ESLint, formatting
  and generated-client drift checks passed. Initial failures were empty alert elements and a
  dynamic record error type; only actual errors now render, and the group message is narrowed.
- Full browser: 25 passed in 2.1m, exit 0, including the real create/response-loss/retry journey.
  Latest shipment-create screenshots at 375/1440 were reviewed: fields, selected quantities,
  action and recovery copy remain readable without horizontal overflow. Dev-only indicator
  appears in the small screenshot; production build does not include the dev indicator.
- Web production image build and isolated Compose startup passed. Schema comparison is clean,
  Worker returned pong and Web health returned HTTP 200. Backend source and migration remain
  unchanged; prior 349-pass backend run is historical, not newly rerun for this UI-only change.
- Remaining V1 scope is unchanged except this form conversion: upload/replacement/connection
  and quotation forms, bounded lists, sensitive fields, real Logto and complete recovery remain.

## Shipment creation retry checkpoint: 2026-09-06

- Shipment creation validates service inputs and uses the shared transactional command-key
  mechanism. Same-key/same-body retries read the scoped original resource's current state and
  current required-document gaps; changed bodies conflict without additional facts. HTTP header
  omission remains a new command for legacy callers, not deduplication. Empty/blank/oversized
  supplied keys fail. The application service requires an explicit key.
- Shipment/items/number/activity/audit/outbox/key are atomic. Shared PostgreSQL upsert numbering
  replaces the old read-then-insert first-number allocation, preserving existing number format.
  New integration tests cover concurrent first shipments for two disjoint orders, same-key
  replay/conflict, different-key capacity competition, permissions/foreign organization, and
  separate activity/audit/outbox failures followed by successful retry. Targeted: 9 passed in
  13.36s. Full backend/Worker: 349 passed in 395.84s, exit 0, one existing Starlette warning.
- Initial rollback tests exposed differing item order between creation and replay; creation now
  returns the repository's stable persisted order. Additional intermediate failures were invalid
  test setup (wrong organization member and duplicate fixture SKU); actual business constraints
  were retained. Strict Python checks pass for all 176 sources; Ruff and formatting pass.
- Browser creates retain a synchronous ref-held key for an unchanged payload and rotate after
  edits. Failure retains input and catches the rejected mutation; pending fields/cancel are
  disabled. Closing/reopening is not durable recovery, and guidance tells users to inspect the
  shipment list before modifying/discarding a form after uncertain completion.
- Real browser test commits creation, aborts its response and retries the retained form with
  the same key. Two POST attempts yield one shipment row, then the normal booking/document/
  delivery/settlement journey continues. Final browser: 25 passed in 2.3m, exit 0. An earlier
  25-pass run preceded a header spelling correction and is not the final fixed-source evidence.
- Frontend full: 112 passed / 30 files in 9.18s. Strict TypeScript, scoped ESLint and client drift
  checks pass. An intermediate production build correctly rejected the header property spelling;
  frontend now matches the generated lowercase field. Final Web production build passes.
- API/Worker/beat images built, final isolated Compose startup passed; Alembic head remains
  20260906_0023, metadata check is clean, Worker returned pong and Web health returned HTTP 200.
  No migration, dependency, role-policy change or main-runtime recreation. Isolated containers
  stopped after checks with volumes retained. The image tag was rebuilt; main containers were
  not restarted against it.
- This closes keyed shipment creation retries, not the remaining RHF/Zod creation/upload/
  connection forms, bounded legacy lists, sensitive fields, real Logto or full-system recovery.

## Shipment booking and write-control checkpoint: 2026-09-06

- Booking now uses RHF/Zod: trimmed nonempty reference up to 120 characters, field-linked
  errors, first-invalid focus, retained failure input and disabled pending fields/button. The
  existing domain command remains authoritative; editor identity follows shipment ID/status.
- Creation, milestone and upload/replacement controls check shipment.write,
  shipment.transition and document.write respectively using scoped member context. Unknown
  permissions expose no writes; delivered shipments retain read-only documents. Pending uploads
  prevent file/type changes. This changes no backend grants or sensitive-field serialization.
- Frontend full: 111 passed across 30 files in 7.54s; targeted shipment tests include read-only
  controls, blank/oversized reference, focus, failed retry payload and pending protection.
  An initial failure was an incomplete mocked problem response; the fixture now matches the
  problem contract. Strict TypeScript, scoped ESLint, formatting and client drift checks passed.
- Full browser passed 25 tests in 2.1m, then passed 25 again in 2.1m after adding explicit
  session-change notification at the shipment role switch and booking screenshots. The final
  run retains the commercial/financial/file journey. Booking at 375/1440 was visually reviewed:
  label, entered reference and action are readable, with no horizontal overflow.
- Web production image build and isolated Compose startup/configuration passed; schema check
  found no operations, Worker returned pong and Web health returned HTTP 200. The isolated
  project was stopped with volumes retained; the main environment was untouched.
- Backend source, migration and API contracts were unchanged. No new full backend-suite run
  was needed for this UI-only slice; the prior 340-pass result is historical backend evidence,
  not a newly executed result. No new dependencies or architecture decisions were introduced.
- Creation/upload/connection form conversion, shipment creation keyed retries, legacy list
  navigation, sensitive fields, real Logto and full-system recovery are still open. UI control
  visibility does not prove authorization, durable retry safety or complete V1 acceptance.

## Purchase creation retry and receiving editor checkpoint: 2026-09-06

- Purchase creation now uses the existing transactional command-key store and advisory lock.
  Explicit Idempotency-Key retries replay the scoped original resource's current state, including
  after approval; changed payloads conflict. Purchase/items/number/activity/audit/outbox/key
  commit or roll back together. No migration was needed; schema head remains 0023.
- The HTTP header stays optional for existing callers. Omission deliberately creates a new
  command, so identical unkeyed partial purchases are not deduplicated. Empty/blank/oversized
  supplied keys are rejected. All first-party creates retain a synchronous ref-held key for
  unchanged payload retries; changed input rotates it. Closing/reopening is not durable recovery.
- Eight new backend cases cover replay, conflicts, permissions/tenant isolation, legacy no-key
  behavior, individual evidence-insertion rollback and competing same/different-key commands.
  Targeted suite: 8 passed; related suite: 62 passed in 94.57s. Full backend: 340 passed in
  379.90s, exit 0, with the two existing warnings.
- Real browser response-loss test commits the initial purchase then aborts the response.
  Retained-form retry uses the same key and yields exactly one purchase card across two attempts.
- A subsequent browser run exposed a receiving editor race: a query version refresh could
  unmount the mutation observer before its success callback and automatically show the closure
  form. Editor state now binds explicit receive/close mode to the version at opening. Refresh
  invalidates the old editor; closure requires an explicit user action. Two deterministic
  rerender tests cover received, partial-receipt and closed transitions without implicit commands.
- Intermediate browser failures are retained as diagnostic evidence, not acceptance: an immediate
  resize assertion was changed to poll the same no-overflow condition; the closure timeout led
  to the production editor fix above. Final fixed-source full browser: 25 passed in 2.0m, exit 0.
- Final frontend: 107 passed across 30 files. Lint, strict Python/TypeScript checks, formatting
  and generated OpenAPI/client drift checks passed. Web production image build and isolated
  Compose startup passed. Runtime Alembic current is 20260906_0023, metadata check is clean,
  Worker returned pong and Web health returned HTTP 200.
- Latest purchase-create and receiving-history screenshots at 375/1440 widths were inspected:
  fields, recovery guidance and closed-state history are readable without horizontal clipping.
  Existing untranslated procurement history remains a polish follow-up, not a new regression.
- No role grants, sensitive-field policy, external account or main runtime were changed.
  Broader form conversion, real Logto, full recovery and sensitive-response acceptance remain open.

## Order form standards checkpoint: 2026-09-06

- Create-order, create-purchase, supplier-confirmation and isolated-test connection forms now
  use RHF/Zod. Field-level alerts and first-invalid focus, pending input/cancel protection and
  retained failure values preserve the existing workbench layout. Payload amounts/rates stay
  decimal strings; validation never replaces backend capacity, state or transaction authority.
- Buttons now check order.write/order.confirm/procurement.write/procurement.approve as applicable.
  Unknown permissions expose no write controls; finalized orders do not offer new procurement.
  This does not fix sensitive cost/profit serialization or change role grants.
- Frontend full: 103 passed / 30 files. Tests cover deposit bounds/calendar validity, exact large
  costs/eight-place rates, rejected-purchase input retention, pending protection, supplier
  confirmation, read-only controls and completed-order restrictions. Initial test issues were
  an ambiguous text locator, an incomplete problem fixture and unsupported test locator options;
  corrected final tests and strict types pass.
- First browser run failed at manager confirmation: the test's per-navigation init script
  overwrote the switched token with SALES on reload. Tests now dispatch the existing session
  change notification, not reload or weaken permissions. Corrected full browser: 25 passed in
  1.8 minutes, exit 0. Primary journey includes order/procurement/receipt/shipping/refund.
- Order-create and purchase-create screenshots at 375/1440 reviewed, no horizontal overflow.
  ui-ux-pro-max guided inline errors, pending feedback and permission-safe interaction; existing
  visuals retained. Code-simplifier review kept local schemas and explicit payload mapping,
  removed parallel quantity/cost state and avoided broader monetary-display refactoring.
- Lint, strict Python/TypeScript, formatting and generated-client drift passed. Web production
  build and isolated startup passed; Alembic 0023/check clean, Worker pong, Web health 200.
  Backend unchanged since the preceding 332-test full pass; not claimed as a new backend run.
  Isolated containers stopped with volumes retained; main runtime untouched.
- Source review found purchase creation lacks a durable command key. The UI warns to check the
  list after connection loss before retrying; durable deduplication remains an implementation
  gap, not solved by disabling the submit button. Quotation/shipment legacy forms remain open.

## Order list query bound checkpoint: 2026-09-06

- Sales order list now fetches active line snapshots in one organization-scoped batch instead
  of one query per order. Existing response, line-number ordering, permissions, amounts and
  command locking remain unchanged. Empty ID batches issue no line query; no migration needed.
- Real PostgreSQL test constructs six accepted quotation/order snapshots and compares complete
  serialized list responses with creation responses. Page limits 1/6/100 each use two business
  SELECTs; foreign-organization IDs return no lines, soft-deleted orders/lines are excluded,
  denied service access returns 403 and reads leave activity/audit/outbox unchanged.
- Targeted order/query suite: 4 passed in 6.94 seconds. Final full backend: 332 passed in
  321.61 seconds, exit 0 (two known warnings). Full browser: 25 passed in 2.2 minutes, exit 0.
  Frontend source was unchanged; earlier 95-test frontend result remains applicable, not a new run.
  Source stayed fixed during final backend/browser runs.
- Lint, strict Python (176 sources)/TypeScript, formatting and generated-client drift passed.
  Code-simplifier review kept a single explicit batch repository method and a simple mapping.
  Isolated API/Worker/beat build/start, Alembic 0023/check, Worker pong and Web health 200 passed.
  Initial Worker probe used an incorrect module name; rerunning with configured worker.app passed.
  Isolated containers stopped and volumes retained; main runtime untouched.
- This removes order-list N+1 only. Existing bounded lists still need navigation review;
  legacy forms, sensitive-field policy and real identity acceptance remain open.

## Quotation validity checkpoint: 2026-09-06

- Acceptance now checks the inclusive organization-local valid_until date after acquiring locks,
  using the same captured UTC instant for accepted_at. Expiration returns
  QUOTATION_VALIDITY_ENDED (409), without an implicit EXPIRED transition or partial evidence.
  Existing accepted retries and subsequent order creation preserve historical facts; recovery
  requires a new revision and normal approval/send. Identity owns the scoped timezone reader.
- Fourteen new tests cover SENT/CUSTOMER_REVIEW midnight boundaries in Shanghai, Los Angeles
  and UTC, unchanged rejection evidence, historical replay/orders and revision recovery.
  Initial targeted failures were incorrect test evidence counts: acceptance also records CRM WON.
  Corrected targeted suite: 24 passed in 22.69 seconds. Final full backend: 331 passed in
  327.97 seconds, exit 0, with two known upstream/config warnings.
- Full frontend: 95 passed / 29 files. Full browser: 25 passed in 2.3 minutes, exit 0,
  including visible expired-acceptance rejection followed by revision and the commercial journey.
  Source stayed fixed during full backend/browser runs. No production frontend visual changes.
- Lint, strict Python (176 sources)/TypeScript, formatting and generated-client drift passed.
  Code-simplifier review retained one clock instant and a small identity-owned timezone port.
  No schema/API-shape change; migration head remains 0023.
- API/Worker/beat images rebuilt and isolated startup passed; unchanged Web image reused.
  All healthchecked services healthy, beat running, Alembic 0023/check clean, Worker pong,
  Web health 200. Isolated containers stopped with volumes retained; main runtime untouched.
  This closes quotation validity, not sensitive-field policy, real Logto or full V1 acceptance.

## Customer review transition checkpoint: 2026-09-06

- Guide 5.3's existing CUSTOMER_REVIEW state now has a mark-customer-review command and
  permission-gated browser form. Requires quotation.send, displayed version ID, nonempty
  evidence reason and durable Idempotency-Key. It records a human-observed review start only,
  never sends a message, changes commercial amounts or accepts the quote for the customer.
- Quotation/current-version locks reject non-SENT states and stale revisions. Identical replay
  returns the original version ID, including after later acceptance, with no new audit/activity/
  outbox. Different request with the same key conflicts. Separate competing commands have one
  winner; evidence failures roll back both status and command key. Event name is
  quotation.customer_review_started.v1; evidence reason remains in activity/audit, not outbox.
- Existing database status constraints already contain CUSTOMER_REVIEW. No schema change or
  artificial migration was added; migration head remains 0023. Existing accept/reject and
  revision behavior is retained. Generated API includes the new explicit route before the
  legacy generic accept/reject route so route matching cannot shadow it.
- Initial customer-review and quotation suite: 10 passed in 10.45 seconds. Frontend full:
  95 passed / 29 files. Final full browser: 25 passed in 2.2 minutes; primary journey now records
  customer review before acceptance and then completes procurement/payment/delivery/refund.
  Final full backend: 317 passed in 310.26 seconds with two known upstream/config warnings.
  Source remained unchanged during final full backend and browser runs.
- New form uses RHF/Zod, preserves displayed version and unchanged retry key, disables pending
  edits, shows errors and omits unauthorized controls. UI skills retain the existing quotation
  visual system and explicit non-acceptance wording; 375/1440 screenshots visually reviewed with
  no horizontal overflow. Code-simplifier review retained the existing shared evidence writer
  with an optional reason rather than duplicating activity/audit/outbox logic.
- Lint, Python (175 sources)/TypeScript, format and generated client drift passed. Complete
  isolated Compose rebuild/start passed, Alembic 0023/check clean, Worker pong, all healthchecked
  services healthy/beat running and Web health 200. Isolated containers stopped, volumes retained;
  main runtime unchanged. Fixture browser identity does not establish real Logto acceptance.

## Product directory navigation checkpoint: 2026-09-06

- 0023 adds an active organization/name/id index and data-preserving downgrade. Product list
  retains count as current page size and adds has_more/next_cursor, with 1–100 rows per page
  and 50 by default. Equal names use UUID tie-breaking; foreign/missing/deleted anchors return 404. Search percent/underscore/backslash are literal, not caller-controlled SQL wildcards.
- UI provides previous/next product pages, scoped query keys, page-one reset on submitted search,
  pending/error navigation protection and existing workbench styling. Product creates and all
  existing commercial snapshots remain unchanged. Read navigation writes no audit/outbox.
- New backend cases prove 105 equal-name products across three pages, foreign-organization
  exclusion, literal search, soft-delete behavior, input limits, query-service permission denial
  and 0022 upgrade/downgrade product preservation. Product/supplier/migration suite: 27 passed
  in 21.95 seconds. Final full backend: 311 passed in 300.96 seconds (two known upstream/config
  warnings, no failures). Source was held fixed throughout full backend/browser regression.
- Frontend full suite: 93 passed / 28 files. Full browser: 25 passed in 2.1 minutes, including
  actual creation/navigation to product 51, backward navigation and filtered page reset, plus
  the complete existing order/refund journey. 375/1440 pagination screenshots visually reviewed;
  no horizontal overflow, reduced-motion mode and explicit disabled navigation verified.
- Lint, strict Python (175 sources)/TypeScript, formatting and generated client drift passed.
  Code-simplifier review retained explicit small pagination operations and existing UI tokens;
  no broad abstraction or dependency was introduced. Initial formatting command could not find
  Prettier through pnpm exec; the installed Node entry point succeeded, followed by full checks.
- Isolated complete Compose build/start passed; Alembic 0023 head and metadata clean, Worker
  pong, Web health 200 and all healthchecked services healthy/beat running. Isolated containers
  stopped with volumes retained. Main running environment was not recreated or upgraded.
- Confirmed remaining gaps include sensitive cost/profit response policy and old business forms
  lacking RHF/Zod. Real Logto and initialized full-system restoration remain unaccepted.

## Safe operational observability checkpoint: 2026-09-06

- ADR-019/0022 adds ADMIN-only organization monitoring, seven bounded aggregate queries,
  explicit unknown-cost/no-decision states, per-process 256-organization LRU request samples
  and internal connection-pool diagnostics. Reads do not create recursive audit/outbox events.
  Queue age is durable event age pending its exact consumer receipt, not Redis queue length.
- API and Celery logs allowlist structured observations and never format raw library messages,
  exceptions, arguments or results. API records route templates rather than sensitive raw paths.
  Logging failures do not turn a committed command into an apparent failure. UI uses existing
  workbench tokens and explains reset windows, upload errors and the placeholder scan framework.
- Before final startup hardening: full backend 308 passed in 298.26 seconds; frontend 91 passed
  in 27 files; full browser 24 passed in 2.0 minutes. Operations screenshots at 375/1440 were
  visually inspected without horizontal overflow. Strict Python (175 sources)/TypeScript,
  lint, format and generated client drift passed.
- Initial container inspection exposed two API startup lines and 25 Worker banner lines outside
  JSON. Added Uvicorn logging config, early warning capture and Celery/beat --quiet; rebuilt and
  restarted the complete isolated stack successfully. Eight safe-logging tests and static checks
  passed after this hardening. Final full backend after hardening: 308 passed in 260.69 seconds.
  Only the known disabled-cache-plugin/upstream Starlette warnings remained.
- Final live log snapshot: API 89 JSON / 0 other lines, Worker 678 / 0, beat 227 / 0.
  A synthetic request with secret query/Authorization header returned 200, and a real Celery
  tenant-context probe with a secret extra context field succeeded. All three logs omitted the
  marker; API and Worker retained request ID 8af68434-5d6d-4829-ba98-4bc866e3615e.
  Probe uses a synthetic organization and does not write commercial data or establish identity.
- All healthchecked isolated services healthy; beat running. The main environment was not
  recreated. Final Alembic 0022 head/check clean, Worker pong and Web health HTTP 200.
  Real Logto login, initialized full-system recovery and the remaining guide audit
  are still open; these checks are not a V1 release certificate.

## Organization and membership administration checkpoint: 2026-09-06

- ADR-018/0021 adds current-organization name/timezone settings and explicit membership grants,
  role changes, disable/reactivate commands. All management routes require ADMIN permissions.
  Commands lock the organization and reauthorize the actor before idempotency and target access;
  concurrent mutual demotions cannot remove both administrators. Existing global identity data
  is never updated by an organization administrator. Login accounts/passwords remain Logto-owned.
- All five command kinds atomically write activity/audit/ID-only outbox and durable command keys;
  version checks reject stale forms. Self-demotion/disable returns an ID without a post-commit
  privileged read, then the UI refreshes actual permissions. Migration 0021 only adds an
  organization/created_at/id cursor index; downgrade preserves all identity and membership facts.
- Initial identity PostgreSQL suite: 19 passed. Added five further cases for settings validation/
  replay/version, cursor and foreign command scope, disabled/deleted global users and 0020
  upgrade/downgrade data preservation. Final full backend: 298 passed in 311.30 seconds,
  including all 24 identity tests and migration schema/index checks. The initial full run
  had 291 passed / 2 failed because test HEAD still expected 0020; that run was not a pass.
- Final frontend: 89 passed / 26 files. Final full browser: 23 passed in 2.3 minutes, including
  real browser settings/add/role/disable/reactivate and last-admin rejection. The initial new
  browser case used an unsuitable exact label locator; changed to semantic combobox role,
  separately passed in 45.6 seconds and then passed in the full run. Earlier 22/23 is not a pass.
- 375/1440 screenshots visually reviewed with no horizontal overflow. UI skills preserve the
  existing workbench visual system and emphasize verified identity, reason and confirmation;
  code-simplifier centralized member response serialization and mode-specific form fields.
- Final lint, strict Python (170 sources)/TypeScript, formatting and generated client drift
  passed. Isolated Compose builds/start succeeded, Alembic 0021 head and schema check clean,
  Worker pong, all healthchecked services healthy and beat running, Web health 200. Final Web
  rebuild after form simplification also passed. Isolated containers stopped, volumes retained;
  main running environment was not upgraded or recreated.
- Auth session remains configured=false/authenticated=false/test_bearer=false in the isolated
  production-mode build. Browser tests explicitly use a local test identity; not real Logto login.
  An asynchronous question requests a local acceptance administrator email; password must be
  set directly by the user, not supplied in chat. Observability gap confirmed during guide audit
  and retained in REMAINING_SCOPE; this checkpoint does not finish V1 acceptance.

## Supplier payable and outgoing settlement checkpoint: 2026-09-06

- ADR-017/0020 implements payables, supplier_payments and supplier_payment_allocations separately
  from customer receipts and ancillary expenses. Payables copy confirmed purchase supplier/currency,
  require human invoice evidence and cap active principal at original purchase total; no backfill
  invents obligations or cash. Zero-net void preserves original evidence. Procurement cancellation
  and closure never automatically settle debt, and supplier finance never changes customer states.
- ADMIN/MANAGER/FINANCE explicit permissions gate reads/writes. Positive same-supplier/same-currency
  allocations lock payment then sorted payables, validate opening versions and both available
  balances. Reversal appends payment/allocation facts and restores derived payable balance without
  claiming a bank refund. All five commands atomically write activity/audit/ID-only outbox and
  durable keys. Payment creation uses company KEY SHARE; a directed concurrency test proves that
  this lock remains compatible with reversal FK checks while recording waits for numbering.
- PostgreSQL full regression: 272 passed in 315.41 seconds. Final supplier suite: 29 passed in
  40.38 seconds after adding two tests for multi-payable settlement/pagination and competing
  reversals. Full suite was not rerun after those test-only additions. The suite includes fifteen
  independent evidence-failure rollback cases, cap/date/currency/version/permission/tenant/cursor
  guards, repeated allocations/replays, immutable original facts and nonempty downgrade refusal.
  Migration group: 3 passed; 0020 empty upgrade and metadata audit clean. Explicit FK names were
  shortened to meet PostgreSQL's 63-character limit without weakening constraints.
- On-demand purchase-card UI covers payable entry, void, outgoing payment method/date/evidence,
  allocation and reversal, independent 20-row cursors, protected data fetching, reasons and human
  confirmation. Generated contracts, RHF/Zod and unchanged retry keys preserve opening versions.
  Supplier payment availability across purchases is not presented as current-purchase settlement.
- Frontend final 86 passed/25 files. Full browser 22 passed in 2.0 minutes. Final primary commercial
  journey after behavior-preserving UI simplification passed in 2.3 minutes, including CNY payable,
  outgoing payment, allocation, reversal and corrected payment before the existing full customer
  deposit/delivery/balance/completion/export flow. 375/1440 screenshots visually reviewed without
  overflow. Tests use an explicitly local fixture identity, not real production login. An initial
  E2E reference to an absent finance token was corrected to the existing authorized manager token;
  the interrupted defective run is not acceptance evidence. No production permissions changed.
- Typecheck (165 Python sources plus TypeScript), lint, format and client drift checks passed.
  Formatting now explicitly excludes existing gitignored tmp artifacts; no inaccessible directory
  was deleted or had its permissions changed. Code-simplifier removed nested display branches;
  frontend skills preserved existing ledger tokens and emphasized evidence/confirmation.
- Isolated Compose build/start reached 0020 head, schema check clean, all healthchecked services
  healthy, beat running, Worker pong and Web health 200. Final Web rebuild also passed. Auth
  remains configured=false/authenticated=false/test_bearer=false. Main runtime was not upgraded.
  Isolated containers were stopped after acceptance; all volumes retained.
  Supplier settlement closes this implementation gap only; organization/member administration,
  real Logto, initialized whole-system recovery and remaining guide-wide acceptance stay open.

## Incurred order expenses checkpoint: 2026-09-06

- ADR-016 and migration 0019 add incurred ancillary expense facts, explicit cost classification,
  currency/rate/date/evidence/reason snapshots, full append-only reversal and scoped cursor reads.
  ADMIN/MANAGER/FINANCE only. Confirmed orders permit late costs without reopening finalized
  orders. Net additional costs adjust quoted forecast only; no actual profit or funds transfer
  is inferred. Purchase principal and outgoing settlement remain separate outstanding work.
- Order-first locking, durable keys, opening versions and activity/audit/outbox are atomic.
  Real PostgreSQL tests cover concurrency, tenant/parent/permission guards, illegal inputs,
  rounding/overflow, summary no-double-counting, unchanged original facts and six rollback cases.
  First execution now refreshes stored Decimal precision to match replay serialization.
- Full backend 245 passed in 230.45 seconds. Final expense suite 14 passed in 15.89 seconds after
  strengthening the nonempty downgrade test. Initial expenses+migrations 17 passed. Frontend
  final 83 passed across 24 files, including no-permission/no-profit-fetch and retry/version tests.
  Full browser 22 passed in 1.8 minutes, with expense posting and reversal in the complete
  commercial flow. 375/1440 expense screenshots visually reviewed with no overflow.
- Typecheck (159 Python sources plus TypeScript), lint, formatting and API-client drift passed.
  Isolated Compose build/start reached 0019 head, schema comparison clean, healthchecked services
  healthy, beat running, Worker pong and Web health 200. Auth remains configured=false,
  authenticated=false/test_bearer=false. Isolated containers stopped; volumes retained and main
  environment untouched. Final additions were test-only, not production-image changes.
- Design skills preserved established ledger styles and emphasized manual classification and
  explicit reversal; code-simplifier kept the implementation scoped and removed unused form data.
  This closes expenses only, not payables, organization administration, live login/provider/scanner,
  initialized whole-system recovery or remaining guide-wide acceptance.

## Sales contract evidence checkpoint: 2026-09-06

- ADR-015 freezes order-linked contract drafts, immutable commercial snapshots excluding internal
  cost/profit, external reference/notes maintenance and human signature recording. SIGNED/VOIDED
  are immutable; only draft voiding permits another contract. No legal signing, order-state,
  price, payment or automatic completion side effect is implied. Existing orders are not
  backfilled with invented contracts or forced through a newly inferred contract completion gate.
- Migration 0018 adds sales_contracts, tenant/order/document-version composite foreign keys,
  status/evidence constraints, active uniqueness and cursor index, plus SALES_CONTRACT file type.
  Nonempty contract/file evidence prevents destructive downgrade. Commands use order-first locks,
  opening versions, reasons and durable keys, with atomic order activity/audit/ID-only outbox.
- Manager signature recording verifies a non-future date and exact same-order, same-organization,
  AVAILABLE, checksum/size-matched and storage-pinned file version. Replacement versions do not
  replace signed evidence. Draft and finalized order restrictions, tenant/parent/permission checks,
  concurrent creation and create/signature rollback are covered by PostgreSQL tests.
- Order UI covers draft creation, reference/notes editing, draft voiding, permission-sensitive
  signature/upload controls, document upload/verification status and exact historical download.
  RHF/Zod forms retain opening version and unchanged retry key, confirm consequential actions,
  and use generated API contracts. Contract events use the existing bounded order timeline.
- Full backend: 228 passed in 220.05 seconds. Final contract suite: 17 passed in 18.74 seconds,
  including three added signature-failure rollback cases and a stronger file-replacement test.
  The full suite was not rerun after these test-only additions. Frontend: 79 passed across 22 files.
  Full browser: 22 passed in 2.1 minutes; the primary journey uploads a synthetic contract,
  runs the explicitly placeholder scan worker, records signature, then completes the commercial
  deposit/procurement/shipment/balance/export/refund flow. This is not legal document validation.
- Frontend-design/ui-ux-pro-max preserved existing ledger tokens and guided labels/confirmation/
  feedback; 375/1440 contract screenshots were visually reviewed, with overflow assertions.
  Code-simplifier review kept explicit command/validation branches and scoped reused transfer.
  An older order unit-test mock was updated to supply the member-context contract; no production
  permission behavior was weakened to make that test pass.
- Typecheck (155 Python sources plus TypeScript), lint, format and generated-client checks passed.
  Isolated Compose build/start reached 0018, Alembic metadata check clean, healthchecked services
  healthy, beat running, Worker pong and Web health 200. Production auth remains unconfigured,
  unauthenticated and test_bearer=false. Containers stopped with volumes retained; main untouched.
- This closes sales_contracts only. Payables, expenses, organization/member management, real
  Logto login and initialized whole-system recovery, live provider/scanner setup and the broader
  guide-by-guide acceptance audit remain open. These results are not a V1 release certificate.

## Historical receipt navigation checkpoint: 2026-09-06

- Closed the latest-100 organization receipt truncation gap. GET /payments now supports
  server-side customer/currency filters, literal case-insensitive number/reference search,
  and stable received_at/created_at/id cursor navigation. Cross-scope anchors return 404;
  count remains the page size, not a customer balance or organization-wide total.
- Migration 0017 adds organization and customer/currency ordering indexes only. No financial
  records, state rules, existing role grants, settlement locks or atomic audit/outbox writes
  changed. Allocation reads remain one batch per page. ADR-008 remains authoritative.
- Order finance shows 20 matching receipts per page, previous/next controls, reference/date
  evidence and a recoverable query error. Search resets cursor/allocation selection; independent
  receipt loading preserves the recording form. Generated contracts and tenant-scoped cache keys
  are used. No new dependencies. Design skills preserved existing ledger styles; simplifier
  review kept explicit filter construction and removed unnecessary non-null assertions.
- Backend full regression: 214 passed in 188.86 seconds. Targeted finance/navigation/migrations:
  20 passed. Frontend: 74 passed. Full browser regression: 22 passed in 1.7 minutes, including
  21 newer receipts, page-two selection, reference search and deposit/balance allocation before
  delivery/completion. Initial test assumptions were corrected: SALES has existing payment-read
  permission, and error fixtures must supply the complete ProblemDetails contract.
- Format, lint, Python/TypeScript type checks and generated-client drift checks passed. Isolated
  Compose build/start reached 0017 with Alembic check clean, healthy services and Worker pong.
  Production-mode session remains configured=false/authenticated=false/test_bearer=false;
  these checks do not prove real Logto login or whole-system production readiness.
- Final pagination spacing reuses queue-pagination; final primary browser journey passed
  (1.2-minute journey, 1.5-minute run). Final Web image rebuild passed and returned health 200;
  isolated containers stopped with all volumes retained. Main environment untouched.

## Product supplier reference checkpoint: 2026-09-06

- Migration 0016 adds product_supplier_links with tenant/product/supplier composite constraints,
  active uniqueness, list index, exact price/currency, factory SKU, lead time, quote date/validity
  and source reference. Reference changes never rewrite product costs or sent quotation snapshots.
  No purchase commitment, supplier acceptance, delete or identity move is implied.
- Create/update commands enforce supplier role, reason/version/idempotency and company-first locks;
  activity/audit/outbox are atomic. Locked reads refresh cached versions. Supplier names are batched;
  references and history are bounded. Downgrade refuses to destroy a nonempty reference table.
- Explicit supplier-price permissions hide this data from VIEWER, allow FINANCE reads, and allow
  ADMIN/MANAGER/SALES/OPERATIONS writes. The /products UI provides product search, company-name
  supplier selection, reference forms and history with generated contracts and scoped caches.
- Full backend regression: 210 passed in 195.68 seconds. Final supplier suite: 21 passed in
  15.80 seconds, including added cursor/locked-cache checks and a strengthened SENT quote test.
  Initial supplier + migration checks: 23 passed. Frontend suite: 72 passed; no new dependencies.
- Supplier browser journey passed (6.6 seconds). Initial full browser run lost an existing receipt
  success notice while code was being edited; the saved receipt was present. No finance logic was
  changed. With source held fixed, full browser regression passed 22/22 in 1.9 minutes. A precise
  root cause for the transient notice loss is not proved; do not describe it as a funds failure.
- Frontend-design/ui-ux-pro-max preserved ledger colors/type and guided search-first selection;
  reviewed 375/1440 screenshots show no overflow. Code-simplifier kept explicit create/update
  dispatch, small field rendering metadata and stable retry state; final lint is clean.
- Isolated production images built/started, 0016 head and Alembic metadata check clean, services
  healthy and Worker pong. Production-mode auth remains unconfigured; main environment unchanged.
  Isolated containers stopped after acceptance; containers and volumes retained.
- This closes product_supplier_links only. Contracts, payables/expenses, organization/member
  administration and complete real-auth/recovery/acceptance work remain. Product search still uses
  the existing 50-result bound with a visible refine-search notice; receipts still need bounded
  search/cursor follow-up noted in the remaining scope ledger.

## Company/contact archive checkpoint: 2026-09-06

- Added tenant name/role cursor list, company detail/update/create, contact list/read/create/update
  and bounded activity history APIs. Shared normalization with lead conversion prevents separate
  customer/supplier duplicates. Writes preserve role/parent identity and use reason/version/key,
  atomic audit/activity/outbox; no delete, merge, contact move or historical order rewrite.
- Migration 0015 adds company/contact navigation indexes only. API/Worker typecheck, Ruff and
  generated-client drift checks passed. Archive + migration tests 12 passed; final permission
  check uses an actual finance member and returns 403, with 9 archive tests passing.
- Added /companies list/detail, submitted name/role search, cursor pages, company/contact forms,
  add-only roles, bounded history and homepage navigation. RHF/Zod and generated contracts enforce
  input feedback; server permissions hide writes, forms disable pending edits, and unchanged retries
  retain command keys. Opening versions survive background refresh. Websites are displayed as text,
  not arbitrary clickable schemes; outbox contains IDs, not contact fields.
- Browser testing found and fixed two real issues: query-refresh remounts suppressed success
  feedback, and the same-origin proxy did not expose PUT. PUT now reuses origin validation and
  server session token forwarding, with exact body/tenant/key and cross-origin rejection tests.
- Full backend regression: 190 passed in 161.75 seconds. Frontend: 68 passed across 19 files.
  Full browser run: 20 passed, company journey failed only at a test locator for the role filter;
  corrected to an accessible combobox locator, then that full company journey passed in 6.4 seconds
  (20.5 seconds including setup). Do not describe this as a single 21/21 run.
- Typecheck (147 Python source files plus TS), lint, formatting, generated-client drift and Compose
  config passed. Isolated images rebuilt/started; healthchecked services healthy, Worker pong,
  migration 0015 head, Alembic check clean, Web /api/health 200. Isolated stack stopped afterward,
  containers/volumes retained. Main Web/API/database were not upgraded.
- Frontend-design/ui-ux-pro-max guided reuse of ledger tokens; 375/1440 screenshots reviewed with
  no horizontal overflow. Code-simplifier review kept explicit command dispatch and shared small
  field/actions/pager helpers without introducing a generalized form framework.
- This closes the company/contact archive slice only. Real auth remains configured=false and
  test_bearer=false in production-mode isolation. Continue product_supplier_links and the remaining
  named slices/acceptance work; all goal scope remains active.

## Opportunity lifecycle checkpoint: 2026-09-06

- ADR-014/migration 0014 add loss evidence and tenant list index. Explicit negotiation/loss
  require permissions, reason, version and command key. WON/LOST are terminal. Inquiry and
  quotation progress now use a CRM-owned transaction port with separate atomic evidence.
  Concurrent loss/acceptance has one winner; accepting a LOST opportunity is rejected without
  partially accepting the quotation. No quote withdrawal or customer notification is performed.
- Added stage-filtered list, detail, history, permission-sensitive confirmation forms and homepage
  navigation. Frontend-design/ui-ux-pro-max guided reuse of existing ledger tokens. Screenshot
  review at 375/1440 corrected mobile refresh wrapping; no horizontal overflow. Code-simplifier
  removed duplicate tenant checks after filtered reads and clarified cancel/success feedback.
- Full API/Worker suite 179 passed (170.68 seconds), followed by final 9-test opportunity suite
  including two added previous-data/downgrade and cursor isolation cases. Frontend 60 passed;
  full Playwright 20 passed (2.0 minutes), including persisted loss and complete commercial flow.
  Typecheck, lint, format and generated-client drift checks passed.
- Isolated production Compose images built/started: healthchecked services healthy, beat running,
  Worker pong, 0014 head and no Alembic drift, Web /api/health 200. Production auth remains
  unconfigured with test_bearer=false. Main Web/API/database were not upgraded.
- This checkpoint closes only opportunity lifecycle scope. Four named model slices, company/
  contact management, organization/member administration and full acceptance gaps remain open.
- Final extended commercial browser journey also passed (1 test, 1.3 minutes), now explicitly
  navigating to opportunity negotiation and back to quotation acceptance before fulfilling the
  complete order/refund chain. Isolated containers were stopped after checks; volumes retained.

## Procurement cancellation/replacement checkpoint: 2026-09-06

- ADR-013/migration 0013 preserve original commitments and received facts; only unreceived
  quantities are released. Linked replacement drafts require normal approval/send/confirmation.
  Commands require procurement.approve, version, idempotency key, reason and supplier evidence
  after sending. No return, legal settlement, outgoing message or payment reversal is implied.
- API returns original and retained totals separately; the UI sums retained amounts with exact
  fixed-four-place arithmetic. Code-simplifier review removed nested submit-label conditions.
- Full API/Worker run: 170 passed in 170.27 seconds. Two subsequent foreign-supplier/terminal
  tests passed in the final 16-test procurement-change suite. Coverage includes authorized
  cross-tenant rejection, receipt/cancel races, idempotency, failed replacement rollback,
  activity/audit/outbox failures, and upgrade from 0012 with existing receipt quantities.
- Initial full run had 160 passes and one temporary-directory setup permission error. A new
  project-local temporary directory resolved it; no old temporary data was deleted. Remaining
  warnings concern disabled pytest cache configuration and upstream TestClient deprecation.
- Frontend 57 passed; full Playwright 20 passed (1.8 minutes), including amendment, replacement
  reapproval, partial/full receipt, closure, delivery, deposit/balance, completion and refund.
  Typecheck, lint, formatting and generated-client drift checks passed.
- Isolated Compose production images built and started successfully. All healthchecked services
  healthy, beat running, Worker pong, migration 0013 head and no Alembic drift. Web /api/health
  returned 200. Production auth remains unconfigured and fixture bearer mode disabled.
- Main Web/API/database were not upgraded. Remaining business/admin modules, real Logto login,
  full initialized-system recovery and other acceptance gaps remain open in REMAINING_SCOPE.md.
- Isolated services stopped after verification; containers and volumes retained. Formatter commands
  explicitly prune test cache trees before traversal, avoiding Windows ACL scan errors even when
  those trees are already in .prettierignore. Source formatting coverage is unchanged.

## Procurement receiving checkpoint: 2026-09-06

- Migration 0012 adds bounded received quantities without changing original quantities/prices,
  plus received/closed UTC timestamps. Upgrade from prior purchase data preserves commitments;
  Alembic check passes. Legacy receipt statuses stop migration for evidence reconciliation;
  downgrade refuses to discard receipt facts.
- Explicit receive/close commands require permission, current version and durable idempotency
  keys. Partial/full receipt states are derived; over-receipt and premature closure fail.
  Receipt reference/date/line increments and closure reason are atomic with audit/outbox/activity.
  Organization timezone governs receipt dates. Closure is fulfillment, not supplier settlement.
- Web procurement cards support partial receipt, closure and paginated operation history.
  Existing UI tokens retained; 375/1440 screenshots inspected. No horizontal overflow detected.
- Full backend/worker suite 155 passed (128.97 seconds); an additional activity-failure case
  then passed in the 6-test targeted receiving suite. Frontend 53 passed. Full browser suite
  20 passed (1.7 minutes), including two receipts, closure and history in the commercial chain.
  Final retry-key implementation also passed unit tests, production build and a repeated
  full commercial browser journey (1 passed, 2.2 minutes).
- Typecheck, lint, formatting, generated-client checks passed. Isolated Compose images built
  and started; Web/API/PostgreSQL/Redis/MinIO/Worker healthy, beat running, Worker pong,
  migration 0012 head with no metadata drift. Main Web/API and main database remain unchanged.
  Isolated services were stopped after checks; containers and volumes retained. Web health
  returned 200; production auth remained unconfigured with fixture bearer mode disabled.
- Procurement cancellation/amendment handling is still open, along with the other named V1
  gaps and real Logto initialization. This checkpoint does not certify full V1 completion.

## Failed event administration checkpoint: 2026-09-06

- `/admin/outbox` implemented with permission-aware tenant listing, bounded pagination,
  sanitized errors, replay reason, explicit confirmation and optimistic version checks.
  Successful replay says requeued, not processed. Homepage link follows read permission.
- Replay now locks the row and rolls back the entire transaction if audit recording fails.
  No schema migration is needed; existing event version and audit fields are reused.
- Related API/platform suite: 41 passed. Frontend suite: 50 passed. Actual isolated browser
  replay test passed; 375/1440 screenshots inspected with no horizontal overflow.
- Typecheck, lint, production build, format and generated-client drift checks passed.
  Full Python/API/Worker regression: 150 passed (116.19 seconds); full browser suite:
  20 passed (1.7 minutes), including the commercial chain and manual event replay.
  Docker Compose configuration validation also passed. No new image startup was claimed.
- This feature is not yet deployed to main Web/API; real login still awaits initialization.
  Remaining named business/admin slices and full V1 acceptance remain open.

## Latest infrastructure checkpoint: 2026-09-06

- Paired DB/MinIO recovery passed with 38 matching table fingerprints, two pinned historical
  document versions and three actual object versions. Original storage IDs and hashes survived
  restore to empty independent targets; Alembic check clean. No main data was overwritten.
- Full fresh project build/start passed for Web/API/Worker/worker-beat/PostgreSQL/Redis/MinIO.
  Fresh migration 0011 head; all healthchecked services healthy; Worker pong; Web/API ready.
  Unconfigured production login rejects fixture bearer credentials with 401.
- New scripts passed Ruff and formatting, actually ran through backup/restore, and related
  document/platform regression tests passed (13 tests). Main application code was unchanged
  in this checkpoint; previous 145/46/19 full-suite results remain the application baseline.
- After evidence capture, both temporary acceptance stacks were stopped to release resources.
  Containers, named volumes and backup files were retained. Main stack and Logto were not stopped.
- Read `REMAINING_SCOPE.md` before further work: source inspection confirmed additional required
  business/admin gaps. Login is not the only unfinished item. Full V1 acceptance remains open.

## Current checkpoint: 2026-09-06, login integration and recovery acceptance

- Latest full Python/API/Worker suite: **145 passed**, exit 0, 100.06 seconds.
  Frontend **46 passed**; browser business chain **19 passed**, 1.5 minutes.
  Production build, typecheck, lint, formatting and generated client drift checks passed
  for the login slice. Subsequent recovery changes passed typecheck and targeted tests.
- ADR-012 browser session routes, root login/organization gate and own-memberships endpoint
  implemented. Normal sessions never return bearer credentials to browser code. Organization
  changes remount query caches; failed session verification hides business data. Background
  verification of unchanged sessions preserves unfinished inputs. Fixture bearer mode requires
  an explicit non-production flag. Membership tests cover inactive/deleted/foreign identities.
- **Real login is not yet accepted or deployed to the main Web/API.** Local Logto 1.43.0 and
  its separate PostgreSQL 17 instance are running with loopback-only ports. Admin initialization
  is awaiting user approval and user-entered password at `http://localhost:3002`.
  The fresh issuer advertises ES384 by default; configure/verify RS256 for the business API
  before using the existing backend verifier. No admin or business account was silently created.
- Published outbox events without the intended durable consumer receipt can now be recovered
  in bounded batches after 15 minutes, capped at five publications before DEAD. Recovery runs
  every minute; normal consumers use late acknowledgement and worker-loss redelivery.
  Verified concurrent recovery, unrelated-receipt exclusion, retry caps and stable side effects.
- **Real isolated Redis/Worker rehearsal passed** in `trade-recovery-acceptance`: one queued
  job survived Redis restart; another queued synthetic job was deliberately removed using only
  that isolated Redis's FLUSHDB and republished from PostgreSQL. Actual worker receipts and job
  side effects were present once, and two repeated task executions did not modify the job.
  Receipt timestamps were backdated only for synthetic fixture events to avoid a 15-minute wait.
  Main Redis and business data were untouched. Rehearsal volumes retain evidence.
- Recovery repair subsequently deployed to the main worker and worker-beat images. Actual
  Worker pong confirmed; manual bounded recovery invocation completed. Web/API login changes
  remain undeployed pending initialization. Final formatting and lint checks passed.
- Local performance baseline passed: two organizations with 1,000 leads each, 30 shipments,
  one confirmed order; 3 warmups and 60 measured calls per operation, concurrency 1. Latest p95:
  lead list 9.533 ms, overview leads 10.514 ms, overview shipments 13.515 ms, lead create
  14.210 ms, async acceptance 27.488 ms. Shipment checklist SELECT count stayed 3 for pages
  of 1 and 20. Artifact: `test-results/local-api-performance.json`. This measures in-process
  ASGI + real PostgreSQL, not network/TLS, real OIDC, browser rendering or model execution.
- Still open: actual Logto login/logout/callback acceptance and deployment; full DB + versioned
  MinIO + initialized Logto restore; full fresh-environment Web/API startup acceptance; final
  guide-by-guide scope review and three-currency acceptance mapping. Real AI provider remains
  unconfigured. This checkpoint is not V1 release acceptance.

## Previous checkpoint: 2026-09-06, Phase 8 and shipping hardening deployed

- ADR-011 and migration 0011 implement creator-private, tenant-scoped asynchronous AI runs,
  bounded application read tools, fact/inference/draft separation, tool receipts and human
  approval of internal follow-up tasks. No mail sending or core business-state tool exists.
- Malformed and multiple provider tool requests now receive individual denial receipts;
  argument contents remain hash-only. Network-unavailable execution persists a pending job
  and retries through the worker policy, capped at three provider execution attempts.
- Verified independent creation/approval transaction boundaries, role removal, evidence-tool
  requirements, active/stale lease behavior, duplicate completion and concurrent approval.
  Provider-turn tests assert no database connection is checked out during external execution.
- Latest whole Python/API/Worker run: **123 passed**, exit 0, 94.17 seconds, before the later
  duplicate provider-call-ID receipt test. Latest AI-only run: **30 passed**, exit 0.
- Frontend: **23 passed**. Typecheck, client drift, lint and production build passed.
  Combined browser business chain and keyboard skip-link suite: **19 passed**, exit 0,
  1.5 minutes. Mobile Copilot approval screenshot inspected without overflow or the former
  skip-link overlay.
- Phase 8 images rebuilt and running. Actual API migration **0011 head**, no schema drift;
  Worker pong; PostgreSQL/Redis/MinIO readiness green; Web `/copilot` HTTP 200.
- Model tests and browser fixtures use explicit scripted providers, not live OpenAI. No real
  model credentials or quality validation. Missing provider configuration is an explicit error.
- Outstanding: broader read-source coverage, full worker restart/delivery acceptance,
  remaining Documents/Finance/UI follow-ups and all unverified section 18 items.
  Actual Logto login, full DB+MinIO+Logto recovery and measured latency remain open.
- Upgrade rehearsal: backup `backups/20260906-before-0011.dump`, SHA-256
  `E549172A93AAA82E0A29C22C8A2D97863D5B4ED67DE36331E1FABAA7DC288C2D`, restored to
  `trade_workbench_rehearsal_0011_20260906`. Upgrade 0010 to 0011 and metadata comparison
  passed using the newly built image. Main database had zero organizations before backup.
  This remains a database-only rehearsal, not full system recovery acceptance.
- Subsequent shipping ownership hardening (now deployed): Sales owns progress state writes,
  Fulfillment exposes bounded quantity projections. Three SELECTs per progress refresh, not
  per-line queries. Four new tests verify independent activity/audit/outbox rollback of both
  shipment and order, tenant/permission boundaries and constant query count. Three more tests
  protect pending-deposit/final orders. Shipping group: 9 passed. Whole suite before these last
  three tests: 128 passed. Browser: 19 passed, 1.4 minutes. Worker pong and schema check passed
  after deployment. Shipment creation also batches committed quantities. No public API change.
- Historical document downloads verified and deployed: explicit version endpoint and shared
  history UI for Shipment/Export. Real MinIO replacement test verifies fresh old-version URLs,
  latest bytes, pending/foreign-version rejection and download after finalization. Frontend
  25 passed; full Python/Worker suite 131 passed, exit 0. Browser 19 passed, 1.5 minutes,
  including real historical-version download followed by order completion/refund. 375px history
  screenshot inspected without overflow. Production build, typecheck, lint, format and client
  drift checks passed. No migration needed for this additive endpoint.

## Previous checkpoint: 2026-09-06, immutable document versions

- ADR-010 and additive migration 0010 pin the exact MinIO storage version. The literal mutable
  S3 `null` version fails closed. Public browser signing is independent from internal endpoints.
- Replacement upload sessions use optimistic document versions and new keys, preserve old
  evidence, and exclude pending current versions from business checklists. Finalized targets
  reject new uploads/replacements and completion of previously pending uploads.
- Real PostgreSQL + MinIO test reuses the original presigned PUT with different content and
  verifies the authorized download still returns original bytes, including after replacement.
  It also verifies tenant/role/stale-version rejection and pending/available checklist changes.
- Shipment and export UI expose replacement controls; final targets hide upload controls.
  Shared upload code is simplified without changing its checksum/PUT/complete sequence.
- Latest complete Python/API/Worker suite: **91 passed**, exit 0, 46.36 seconds.
  A ready-event fixture now explicitly predates polling, avoiding host/container clock skew.
- Frontend **19 passed**; strict typecheck, lint, formatting, client drift and production build passed.
  Browser **18 passed**, exit 0, 1.2 minutes, including a second invoice version in the complete
  lead-to-order-to-refund journey. The later null-version rejection also has targeted coverage.
- API/Web/Worker/worker-beat images rebuilt and started. Runtime Alembic is **0010 head**,
  metadata comparison has no new operations; API readiness is green and Worker returned pong.
  Web `/export/customs` returned HTTP 200. Live user login is still not accepted.
- Before upgrade: database had zero organizations. Backup `backups/20260906-before-0010.dump`,
  SHA-256 `84DA97602F1416427D5D7A0699530498CCD8C6DA7AB0A2EFD767E2207FBEC83A`.
  Restored independent database `trade_workbench_rehearsal_0010_20260906` upgraded 0009→0010
  and passed schema comparison. Both backup and rehearsal database are retained.
- Still pending in Documents: explicit historical-version download UI, resumable pending uploads,
  old unversioned-object migration, ordinary-identity version-delete denial, expanded rollback/race
  tests and list pagination. Existing order/shipment forms still need RHF/Zod and role-sensitive UI.
- Small refund screenshot inspected: final upload controls now absent, no horizontal overflow.
  Raw English activity summaries and visible skip-link positioning still need UX review.
- Phase 8 and all remaining section 18 obligations below remain open. This is not V1 acceptance.

## Verified in the 2026-09-05 Phase 6 construction run

- PostgreSQL integration: installment totals, duplicate receipt keys, repeat allocations,
  reversal facts and exact net balances, amount/permission/tenant failures, competing
  payments and competing allocations, rollback with outbox failure, and completed order flow.
- New finance and Work HTTP endpoints are included in generated OpenAPI/client.
- Browser journey: lead conversion, quotation V1/V2, manager approval, order with 30% deposit,
  deposit receipt/allocation, purchase commitment, shipment with actual MinIO uploads, full
  delivery, balance receipt/allocation, task resolution, manager completion.
- Playwright: 18 passed, exit code 0. Includes completed financial detail overflow checks at
  375/768/1024/1440 widths. Screenshots are under test-results/finance-completed-*.png.
- Frontend: 14 tests passed; strict typecheck and production Next.js build passed.
- Python/Worker whole suite: 79 passed, including financial waiver debt retention,
  concurrent first-number creation and completion version/role/state rejection.
- The finance-only run passed 14 cases, adding independent Activity/Audit/Outbox
  insertion failure rollback and five cross-organization command rejection checks.
- Migration tests upgraded disposable empty/previous-revision databases to 20260905_0008;
  Alembic metadata comparison passed.
- Docker api/worker/beat/web images built successfully after official-image download retry.
  Compose startup succeeded; API/Web/PostgreSQL/Redis/MinIO/Worker reported healthy.
  Running API Alembic current is 20260905_0008 (head), check has no new operations;
  Celery inspect returned pong.

## Still required before declaring Phase 6 and V1 accepted

### Phase 7 update, 2026-09-06

- Export UI now includes cursor lists, details, manual fact commands, shared evidence uploads,
  downloads, activity pagination and permission-based controls. Follow-up scheduling has a
  versioned reason-required command; final/rejected cases cannot reschedule.
- Overview replaces the stale landing page with eight PostgreSQL action queues. Net unpaid AR
  is filtered before pagination; each queue checks domain permissions. Integration tests cover
  all-queue isolation, live payment effects, and at most three queries per queue.
- Web tests: 16 passed. API/Worker whole suite before the latest three rollback cases: 83 passed.
  Export-specific run: five passed, including separate activity/audit/outbox failure rollback.
- Browser journey now continues from completed order through manual clearance and actual refund.
  Latest Playwright run: 18 passed, 1.2 minutes, exit 0, including process cleanup.
- Windows cleanup now registers test process IDs plus OS creation times and verifies ownership,
  then terminates only their descendants. It no longer identifies processes by listening ports.
- Production build passed before follow-up form addition. Full typecheck passed after addition.
- Runtime Compose has now been upgraded to 0009 after a real database backup and independent
  restore/upgrade rehearsal. API Alembic current is 0009 head; metadata check has no changes;
  Celery returned pong. Local database had zero organizations before the upgrade.
- Backup: `backups/20260906-before-0009.dump`, SHA-256
  `359C355C7A3F9AD75C1BDA42AFE91EBB7F1A20B1F8D3EEFBE28B8B084A58E491`.
  Restored rehearsal database `trade_workbench_rehearsal_20260906` is retained for inspection.
  This is a database-only rehearsal, not the full DB/MinIO/Logto recovery acceptance.
- Most recent API/Worker suite: 87 passed. Frontend: 19 passed, including read-only export UI,
  amount validation and exact four-place refund differences. Difference display was added after
  the container build and needs the next Web rebuild.
- Latest complete browser run: 18 passed, exit 0, 1.2 minutes, now also exercises follow-up
  scheduling and captures refund detail at 375/768/1024/1440. Small/large refund screenshots
  inspected: no horizontal overflow; final-case upload controls and raw English timeline text
  remain UI polish/finality follow-ups.
- Document hardening underway: public MinIO signing endpoint and explicit region configured;
  signing moved outside the business transaction; document list relationships batch-loaded.
  Eight targeted storage/export/shipment tests passed. These changes are not yet in containers.
- Pending: final export UI/security boundary tests and responsive screenshots, additional reminder
  tests, deployment, Phase 8 and full section 18 acceptance. Older status text below is historical.

Phase 7 has now started: ADR-009, customs/refund ORM and schemas, cursor repositories,
batch document checklists, command services and explicit HTTP routes are present.
Migration 20260905_0009 passed disposable migration tests; the real container database
is still at 0008 until this slice is ready for deployment. The manual clearance-to-refund
service journey passed with fake object storage and real PostgreSQL. Export UI, Overview,
extended security/failure tests and browser acceptance are not yet delivered.

- The Web container has also been rebuilt/restarted for the label correction to agreed deposit.
  Never confuse the contractual deposit snapshot with a current unpaid balance.
- Strengthen finance boundary coverage: explicit timezone boundary, financial waiver retention,
  reversal restrictions after shipping/completion and DB relationship tests.
  Independent activity/audit/outbox insertion failures and cross-tenant commands are covered.
- Payment list/search must let the operator locate older receipts, not only the latest 100
  organization-wide rows. Financial forms need role-sensitive visibility and final a11y review.
- Windows Playwright teardown currently identifies listeners by port. Verify process ownership
  before termination; do not permit a test helper to stop an unrelated process.
- Phase 5 audit follow-ups: document new-version operation, file immutability, browser-reachable
  MinIO signing endpoint in Docker, no external network while holding a business DB lock,
  RHF/Zod conversion for earlier order/shipment forms, and bounded query counts.
- Phase 7: customs/refund manual state tracking, document requirements, reminders,
  actual action-oriented Overview and order-to-refund acceptance.
- Phase 8: controlled AI read/draft/tools, human approvals, audit and tenant/permission tests.
- Full guide section 18 acceptance: two organizations, roles, three currencies,
  reliable outbox after Redis/Worker restart and duplicate delivery, clean-environment boot,
  backup/restore rehearsal, and measured read/command performance targets.
- Reconcile all earlier phase completion claims against the implementation guide; older green
  tests do not prove untested requirements. Real production provider/security deployment remains
  separate from a local V1 acceptance demonstration.
