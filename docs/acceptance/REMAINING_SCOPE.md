# Remaining V1 scope audit

Evidence inspected 2026-09-06. This list does not narrow the implementation guide or authorize
silent deferral. Existing green tests demonstrate their tested slices, not all V1 requirements.

## Confirmed implementation gaps

- Latest update2026-09-07: user approved creator-submitted AI candidate review. ADR-026/0033
  now implements preserved revisions, exact disclosure, protected owner responses and independent
  task execution approval; see AI_DISCLOSURE and V1_STATUS. This supersedes the pending question
  and original AI-response source findings below, not real identity/provider/recovery gates.

- 0032 shipment/quotation/inquiry/purchase cursor navigation is verified: full backend942
  passed1414.29s, with targeted migration/six-role checks, frontend217 and browser30. Dedicated
  shipment source-lines was then added and separately verified by source2/related65 tests,
  frontend219, browser31, static/client and isolated runtime checks. These supersede older
  navigation/source-resolution gaps below, not AI disclosure, real login or joint recovery.
  See V1_STATUS for the distinction between the942 baseline and later source tests.

- AI disclosure cannot grant reviewers access to creator-private runs without an explicit
  decision. Pending question: may a creator voluntarily submit one draft for administrator,
  manager or finance review while unsubmitted drafts remain private? No such access expansion
  has been implemented. Source identifiers remain visible and costs prohibited by the already
  accepted user decision; that does not settle private AI-run reviewer access.

- Order cursor navigation is implemented with0031 index and protected DTOs.105-order navigation,
  tie/insertion/deletion/tenant checks and commercial-copy migration preservation passed; frontend211,
  browser29 and isolated0031 build/runtime passed. Full941 passed1307.56s. Shipment source selection now
  explicitly loads older order pages; shipment list itself and dedicated source-ID resolution,
  quotation/inquiry/purchase navigation remain open. See V1_STATUS for evidence boundaries.

- ADR-025 seven shipment milestone guards now implemented: required version/key, current receipt
  replay, booking conflict and parent/source/capacity checks, with coordinated owned UI/callers.
  Existing30/new70 backend and frontend209 passed; static/client checks passed. Expanded lock14,
  browser28 and isolated build/runtime passed; full backend938 passed with1 temporary-directory setup
  error (independent corrected-directory test passed1); a clean full rerun remains. This supersedes the source-only
  guard gap below, not cursor/AI/login/recovery gaps; see V1_STATUS for evidence boundaries.

- Next shipment source inspection (2026-09-07): ShipmentResponse omits the existing ORM version;
  all seven milestone commands remain unguarded, and already-BOOKED retries ignore a changed
  booking reference. The prerequisite lock-order correction is now implemented: sorted parents
  before lines for creation, sorted parents before shipment for all seven milestones; source
  mapping is revalidated after locking and deleted parents rejected. Targeted30 passed including
  parent-wait and reversed combined-order races; static/client checks and isolated build/start/
  migration/worker/health checks passed. Version/key/booking
  guards remain unfinished. Preserve fixed AVAILABLE documents, timestamps, capacity and
  Sales-owned order updates when implementing them. See V1_STATUS for verification boundaries.

- ADR-024 procurement approve/send/confirm guards are implemented: required displayed version/key,
  protected current replay, explicit conflicting supplier facts and finalized-parent rejection.
  Original60/new53 backend, frontend202, static/client and image builds passed. Browser28 and
  isolated runtime passed; full850 passed (1107.06s), before shipment locking. See V1_STATUS. This supersedes legacy purchase decision
  findings below, not shipment/list/AI/auth/recovery gaps.

- ADR-023 order creation recovery/conflict semantics are implemented: optional durable keys,
  normalized request identity, protected live replay and explicit different-deposit rejection
  instead of silently returning an existing order. Existing42/new17 backend passed; frontend199,
  static/client and image builds passed. Final frontend199, browser28 and isolated runtime passed;
  full797 passed (1029.64s), covering ADR-023 before later ADR-024 changes.
  See V1_STATUS. This supersedes order-creation findings below, not purchase/shipment/AI gaps.

- ADR-022 sales-order confirmation guards are implemented and in verification: mandatory row
  version/key, protected current replay, atomic procurement task/evidence and explicit UI retry
  retaining original variables after refresh. Existing12/new16 backend, frontend198, static/client
  checks passed; browser28 and isolated builds/start/runtime passed; full780 passed (970.85s).
  This supersedes the confirm
  gap below, not order creation, purchase/shipment commands, list navigation or AI/auth/recovery.

- Inquiry creation recovery is implemented and in verification: tenant-scoped keys and atomic
  evidence, current protected replay after quotation progress, unchanged first timestamp/key in
  the owned form and synchronous duplicate guard. Backend15, frontend197, full browser28 and
  isolated build/start/runtime passed; full764 passed (974.00s). See V1_STATUS; no-key findings below are
  historical. Other command/list/AI/auth/recovery gaps remain independent.

- Current source follow-up (2026-09-07): SalesOrderCommandService.confirm and shipment book/ready/
  enter-customs/depart/start-transit/arrive/deliver still accept no displayed version/key. Locks
  enforce state rules but not the opening human-decision version. Shipment already-at-target
  returns current facts before checking a changed booking reference; later-state retry has no
  durable receipt. Preserve timestamps, required documents, fulfillment quantity and Sales-owned
  order progress when adding guards. Orders/shipments/quotations/inquiries still have bounded
  recent lists rather than complete cursor navigation. These are inspected gaps, not new changes.
  Order creation is unique by accepted quotation but returns an existing order before comparing
  changed deposit inputs; add explicit request identity without changing accepted snapshots or
  the one-order-per-quotation rule. Purchase approve/send/confirm also remain legacy unguarded
  endpoints, unlike guarded receive/close/cancel/amend. Follow-up must include all owned callers.

- ADR-021 mandatory quotation state guards are implemented and in verification: six command
  paths require displayed version ID/row counter plus key; no unguarded fallback. Explicit retry
  retains the original request across background refresh. The previously shadowed /expire route
  is reachable. Existing41/new54 backend,196 frontend,28 browser and isolated build/start passed;
  full backend749 finished748 passed / 1 old-fixture failure; corrected commercial54 passed.
  Subsequent full764 passed (974.00s). See V1_STATUS for results and run boundaries.
  This supersedes the six-state-command inspection below, not inquiry/list/AI/auth/recovery gaps.

- Quotation creation recovery now has tenant-scoped durable keys and protected current-resource
  replay with atomic evidence/number/CRM rollback; first-party UI retains unchanged retry identity.
  Initial31 backend, final195 frontend, full28 browser and isolated build/start checks passed;
  full backend695 passed with unchanged0030 schema (949.46s).
  See V1_STATUS. Inquiry creation and other unguarded legacy commands remain independent work.

- Read-only follow-up audit identified concrete next seams: InquiryCommandService.create has no
  durable command key; its form constructs received_at anew on every submit, so a later key alone
  would not yield stable retries. Preserve the first submitted timestamp with the unchanged form
  payload. Current quotation submit/approve/send/accept/reject/expire routes accept only the
  quotation ID and resolve the current version at execution: a stale detail screen cannot bind
  the human decision to the version they actually reviewed. Existing status locks prevent illegal
  transitions but do not establish that version precondition. These need separate vertical slices;
  the creation/revision retry work does not close them. Source inspection is not runtime acceptance.

- Procurement0030 now implements independent original text and history review, preserving source
  and commitment facts. Focused27/Frontend194/expanded Browser28 and isolated runtime checks passed;
  full backend finished680 passed / 6 old-fixture failures, with corrected27 targeted tests passed.
  See V1_STATUS for exact results and split-run boundaries, not an all-green full-run claim.
  Shipment direct response inspection identifies booking reference as an identifier, not prose;
  do not invent a review requirement for identifiers or equate this inspection with full acceptance.

- 0029 commercial original-text enforcement is implemented with recorded checkpoint verification:
  Product/Inquiry descriptions, quotation/order descriptions/terms, contract notes/nested text
  have independent reviews and protected service DTOs. Copies preserve original facts without
  inheriting disclosure; omitted contract fields and price-only revision prose stay unchanged.
  RFQ/external contract references are identifiers, not a route for storing costs. See current
  V1_STATUS; this supersedes older source-gap observations below without closing whole V1.

- Customer receipt notes are now protected by independent 0028 review and service projections,
  including create/allocation/reversal replay. Full backend 613, frontend187, browser28 and
  isolated0028 build/start passed. Bank identifiers and selling/receipt amounts remain visible
  under original read rights; identifying references must not contain costs. Other prose groups
  and complete commercial/auth/recovery acceptance remain open; see TEXT_POLICY_SCOPE/V1_STATUS.

- Confirmed identification boundary: company/contact/product names remain visible under original
  business permissions; internal cost/profit must not be entered in those fields. Notes,
  descriptions, terms and historical prose still require human release. Do not expand default
  confidentiality to all business identifiers or claim automated cost detection. ADR-020 and
  the guide record the user's explicit follow-up decision.

- User confirmed default-confidential attachments and free text with authorized human release,
  including historical content. ADR-020 and the guide now record this policy. Enforcement is
  partially implemented: document versions now have content-bound review commands, protected
  service projections/downloads and shared UI with six-role/tenant/replay/change tests. See
  the latest V1_STATUS for exact regression evidence. Free-text outside Documents remains open;
  preserve original records and never treat file type or scan placeholders as human approval.

  Order Work text is now implemented with 0025, detached protected task/activity query and
  completion/DONE replay outputs, exact-version release/restrict commands and shared UI.
  Order-before-task locking and completion rules are preserved. Browser role journey passes;
  the final backend rerun passed 479 tests (see V1_STATUS for first-run migration failures/fixes).
  CRM/company/opportunity/export timeline protection and review are now implemented with final
  regression/browser/runtime verification in progress; standalone source fields remain open;
  changing only the Work router is not a universal timeline fix. The AI order-timeline port
  already selects only event ID/type/time, so do not claim its current summary/details leak.
  Lead notes/source and opportunity lost reasons now have independent 0026 review and protected
  service responses. CRM browser source-release acceptance passed; final full backend regression
  passed 542 tests (V1_STATUS). Contract notes/external references remain a separate open group.

- Current ADR-020 quotation update: detached protected service responses and safe sales costing
  are implemented; final regression/visual acceptance is in progress (see newest V1_STATUS).
  Sales revisions no longer send hidden costs, while unsolved cross-currency costing requires
  manager preparation. The earlier quotation serializer seams below are historical findings,
  not a claim that the latest code still uses unrestricted router DTOs. Wider work timelines,
  tasks, AI history and arbitrary documents/free text remain open and require separate review.

- Quotation revision now supports durable scoped replay and expected-version conflict checks;
  the owned Web editor supplies both guards and freezes its opening snapshot through refetches.
  Legacy omitted guards intentionally retain old behavior, not guarded replay. Earlier
  no-revision-guard statements below are historical; see the newest V1_STATUS checkpoint.
- Revision snapshot gap closed: copied/source-bound lines preserve full historical defaults,
  including SKU/unit; new unsourced lines use current active Product defaults. Backend 363,
  frontend 150/full browser 25 and isolated builds/runtime passed. No historical rewrite.
- Guide 15.8 confirmed quotation/order first-number races are now closed with the shared
  atomic PostgreSQL allocator. Fifteen new tests cover concurrent distinct aggregates,
  organization/type/year partitions and evidence-failure rollback of first/existing sequences.
  Full backend 378/frontend 150/browser 25 and isolated builds/runtime checks passed.
  Historical numbers and API/permission rules are unchanged; no migration is needed.
- Shipment list batching gap closed: populated pages use three business SELECTs, empty pages
  one, instead of 13 for six shipments. Ten new tests preserve scoped snapshots, item ordering,
  evidence invariance and current available/storage-pinned file rules, including invalid and
  foreign evidence. Full backend 388/frontend 150/browser 25 and isolated build/runtime passed.
  Existing bounded list remains distinct from the remaining cursor-navigation work.

- Quotation workspace form conversion is now complete: create, revision, product/inquiry and
  isolated connection use RHF/Zod; write entry/detail controls follow API permissions. Latest
  frontend 149/full browser 25 and production/isolated runtime checks passed. The legacy-form
  references in earlier checkpoints below are historical. Durable create/revision/inquiry
  uncertain-result recovery and sensitive-response policy remain separate implementation work.

- Quotation revision form and detail command gates now passed frontend 145/full browser 25 and
  production/isolated runtime checks. Create/preparation/connection forms remain legacy. Revision
  POST has no durable retry key or expected version precondition; preserve immutable snapshots
  while implementing uncertain-result recovery and stale-editor rejection in a separate API slice.

- Guide 5.3 customer-review transition gap closed: existing CUSTOMER_REVIEW enum previously
  lacked an entry command. New explicit version-bound, reason-required, idempotent operation
  atomically records review-start evidence; backend 317/frontend 95/full browser 25 passed and
  isolated deployment checks passed. No new schema required.
- Guide 4.4 quotation validity gap closed: new acceptance compares valid_until inclusively with
  the organization-local date after acquiring locks. Expired versions return 409 without partial
  facts; accepted replay and downstream orders preserve history. Shanghai/Los Angeles/UTC
  midnight boundaries and revision recovery passed; full backend 331 and full browser 25 passed.

- Guide 14 observability implemented under ADR-019/0022: allowlisted JSON request/task logs,
  bounded per-organization process latency/error samples, internal pool observations and
  PostgreSQL-scoped backlog/age/job/document/AI/approval statistics with ADMIN-only UI/API.
  Final container startup logs have zero non-JSON lines across API/Worker/beat. A synthetic
  secret in HTTP query/header and task context was absent from all three logs; the real HTTP
  request and completed Celery task retained the same correlation ID. See V1_STATUS for
  regression boundaries. This does not provide historical/global monitoring or malware scanning.

These findings come from inspected model registry, registered routers and frontend feature
searches. They are not inferred from a stale plan. Broader guide-by-guide coverage still needs
review, especially remaining form standards, role-sensitive controls and
all named financial/operational acceptance scenarios.

- Product directory cursor gap closed by 0023: organization/name/id ordering, tenant-checked
  anchors, literal search, preserved page-local count and previous/next UI. Specialized backend
  27 passed, frontend 93 passed, full browser 25 passed; 375/1440 screenshots reviewed.
  Full backend 311 passed. Isolated 0023 build/start/migration/schema/Worker/Web checks passed;
  stopped with volumes retained. Other bounded legacy lists remain
  part of the broader guide audit; this change does not silently extend their APIs.
- Confirmed sensitive-response gap: quotation list/detail/command serializers still expose
  cost/profit snapshots without applying profit.read. Sales-order services now project nullable
  protected snapshots for list/detail/create/confirm/completion and replay. Product responses now
  redact standard_cost/cost_currency for SALES/OPERATIONS/VIEWER, and all supplier-reference
  service/API boundaries require profit.read. Apply the accepted policy to the remaining
  read and command responses and AI sources, and test
  serialized absence/null behavior rather than hiding fields only in the browser.
  User has now selected strict cost/profit restriction to ADMIN/MANAGER/FINANCE. ADR-020 records
  that accepted policy and workflow consequences. Implement protected projections, safe sales
  snapshot authoring and operations quantity-only workflows; existing green tests predate
  enforcement. This item is no longer blocked on role-policy choice.
  The catalog slice has six-role and service-level coverage, protected replay denial, unchanged
  ORM facts, manager handoff and actual browser role-switch checks. See V1_STATUS for its
  separate test results; quotation enforcement is not yet delivered. Procurement structured
  query/command/replay protection and manager-pricing/operations-quantity workflow are now
  implemented; broader arbitrary text/documents remain open. See the latest procurement
  checkpoint for verification, including any pending full-suite result. Order snapshot
  enforcement is implemented with six-role and service-command tests; see V1_STATUS for results.
  Inspected implementation seams for the next slice:
  - sales/schemas.py: nullable protected item/version/list fields and generated client are needed.
    sales/routers.py serializes every create/revise/submit/approve/send/accept/reject/expire result;
    application query/command services currently expose ORM tuples, so router-only filtering
    would leave the service boundary open. Preserve internal snapshot ports explicitly.
  - sales/services.py: create currently dumps defaults and pops caller items. Distinguish omitted
    cost inputs before default expansion; reject unauthorized explicit fields before replay.
    Revision must validate caller inputs before merging protected source snapshots. Cost-rate 1
    is valid for matching currencies, not an automatic cross-currency fallback. Changing quote
    currency must not reuse the old cost conversion rate without a valid authorized snapshot.
  - Closed order serializer seam: sales/order_projections.py is now called inside application
    services, including completion. HTTP routers no longer construct unprotected order outputs.
    Internal repositories retain exact financial/fulfillment facts; stored snapshots are unchanged.
  - Closed procurement serializer seam: application services now use shared protected DTOs
    for queries and commands/replays, and history projects only safe operational metadata.
    Creation/approval/cancel/amend require cost authority; quantity workflows remain available.
    Broader free-text references/descriptions and linked binaries still require separate review.
  - AI already checks saved required_permissions on historical list/detail/tool-call reads;
    PROFIT adds profit.read. sales/assistant_queries.py ordinary snapshots omit costs, and AI
    timelines whitelist IDs/types/timestamps without arbitrary bodies. Preserve these controls
    and add role-change regressions; do not assume every historical free-text artifact is safe.
- Order workspace form conversion passed: creation, supplier confirmation and isolated-test
  connection now use RHF/Zod, exact decimal payloads, pending protection and scoped buttons.
  Frontend 103/full browser 25 and Web production/isolated runtime checks passed; 375/1440
  order/purchase form screenshots reviewed. quotation-workspace.tsx and shipment-workspace.tsx
  still contain legacy forms. Conversion must preserve decimal strings and backend authority.
- Shipment booking now uses RHF/Zod with field errors, first-invalid focus, retained failure
  values and pending protection. Creation, transition and upload/replacement controls require
  the corresponding member permission; unknown context does not expose writes.
- Shipment creation RHF/Zod conversion passed: exact positive four-place quantities, optional
  UUID/calendar validation, selected-line payloads, inline errors/focus and stable retry keys.
  Frontend 125/browser 25, production build and isolated runtime checks passed. New 375/1440
  form screenshots inspected. Quotation form conversion remains open.
- Shipment upload/replacement and isolated-test connection RHF/Zod conversion passed. Frontend
  128/browser 25, production build and isolated runtime checks passed. The browser verifies
  real upload/replacement and historical download. Open-form recovery now retains a scoped
  durable upload key across session-create/PUT/complete failures. Both endpoints recover the
  original version; accepted replay returns no PUT URL, pending replay rechecks target/version
  and replacement opening preconditions are retained. Shared shipment/contract/export hooks
  isolate sessions. Backend full 394 plus final targeted 8, frontend 156, full browser 25 and
  final fixed-source primary journey passed; see V1_STATUS exact run boundaries.
  Persisted pending-upload recovery is now closed: explicit document/version resume validates
  reselected name/MIME/size/SHA-256 against PostgreSQL metadata, reauthorizes before/after
  signing and refuses old/rejected/finalized pending versions. Shared controls cover shipment,
  contract and customs/refund evidence without browser credential or PUT URL persistence.
  Full backend 401, frontend 161, browser 25 and isolated builds/runtime passed; browser
  reload/lost-response/mismatch cycles preserve document/version IDs and one completion.
  See the latest V1_STATUS checkpoint for exact evidence and first-run fixture-role failure.
- Shipment creation keyed retry gap closed: scoped transactional replay/conflict handling,
  stable current-resource response, individual evidence rollback and concurrent capacity/first-
  number tests pass. Browser commit-then-lost-response recovery keeps one shipment across two
  attempts. Header omission deliberately remains a new command; closing/reopening does not
  retain keys. Full backend 349/frontend 112/browser 25 and isolated build/start checks pass.
- Purchase-creation keyed retry gap closed: durable transactional replay/conflict handling,
  evidence rollback, permissions and concurrency passed; the browser proves commit-then-lost-
  response recovery with a stable unchanged-form key. The header remains optional for legacy
  callers: omission is a new command, not deduplication. Closing/reopening does not retain keys.
  A receiving editor refresh race was also fixed using explicit version-bound operation state.
  Full backend 340/frontend 107/browser 25 and isolated build/start/runtime checks passed.
- Order-list line loading now uses two business SELECTs for populated pages instead of N+1.
  Exact snapshots, ordering, tenant/deletion filters and evidence invariance are tested;
  full backend 332/full browser 25 and isolated runtime checks passed. Cursor navigation and
  remaining form/field-policy gaps are not closed by this query-only change.
- Receipt search/cursor gap closed by 0017: server-side customer/currency filters, literal
  reference/number search and stable pagination now reach older receipts for allocation.
  Existing read-role policy remains unchanged; review sensitive-field permissions in the broader
  role-control audit. Page counts are not total customer balances.

## Acceptance still requiring evidence or external setup

- Full commercial PostgreSQL + versioned MinIO recovery now passed:45 table fingerprints,
  8 original object versions, settled orders and role/tenant projections; see COMMERCIAL_RECOVERY.
  This supersedes the historical full-commercial recovery gap below, but not initialized Logto
  recovery, real login, production credentials/ownership or external backup arrangements.

- Real Logto initialization/login/logout/callback and issuer algorithm agreement. User was asked
  to approve local test account creation and personally set the administrator password. No
  administrator account was created by the agent. The default fresh issuer advertises ES384;
  the backend now supports explicitly pinned RS256 or ES384 with key/curve validation. Current
  local public discovery/JWKS were verified as ES384/EC/P-384, and 87 authentication/tenant/member
  tests passed. Actual provider configuration, initialized accounts and real redirect login are
  still mandatory before acceptance; generated asymmetric test tokens do not prove real login.
- DB + versioned MinIO restore now proved for synthetic persistent document metadata, including
  old version IDs and an unaccepted overwrite. Initialized Logto recovery and the full commercial
  fixture's recovery are not yet proved by that rehearsal.
- Three-currency mapping is now source-verified: quotation-lifecycle.spec.ts uses EUR quotation/
  receipts, USD base snapshot and CNY procurement; it settles deposit/balance, uploads real
  MinIO evidence, delivers/completes the order and continues to refund. Exact arithmetic is
  additionally tested by test_v1_v2_approval_acceptance_and_three_currency_math. Latest full
  browser 25 passed includes this journey. This remains explicit fixture auth, not real Logto.
- Live AI provider is unconfigured; scripted-provider security tests are not model-quality tests.
  The documented scan/parse placeholder is not a production malware scanner.
- Production region/provider/backup destination and secrets remain user choices; local fixture
  acceptance must not silently become a production deployment claim.

## Newly established infrastructure evidence

- Organization/member administration implemented under ADR-018/0021 with current-organization
  scope, locked reauthorization, last-admin concurrency protection, explicit verified-subject
  grants, retained global identity fields, version/reason/idempotency and atomic evidence.
  Final full backend 298 passed, frontend 89 passed, full browser 23 passed. 0021 isolated
  builds/start/schema/Worker/Web checks passed, screenshots reviewed, containers stopped and
  volumes retained. This closes the named management gap, not real Logto login or observability.

- Supplier payables and outgoing settlements implemented under ADR-017/0020, including protected
  purchase-card UI, posting/void/allocate/reverse commands, derived balances and atomic evidence.
  Full backend 272 passed, final supplier 29 passed, frontend 86 passed, full browser 22 passed and
  final primary journey passed. 0020 isolated build/start/metadata/Worker/Web checks passed.
  See V1_STATUS for exact run boundaries, fixture-only authentication and unchanged main runtime.

- Sales contracts now implemented under ADR-015/0018: immutable selling snapshots, controlled
  draft updates/voiding, manager signature recording pinned to verified order-linked file
  versions, protected queries and order timeline/audit/outbox. Backend full 228 passed; final
  contract suite 17 passed after additional signature rollback tests; frontend 79 and full
  browser 22 passed. Isolated 0018 build/start/health/migration/Worker checks passed; main
  environment untouched and isolated containers stopped with volumes retained.

- Product supplier references now implemented with migration 0016: current supplier SKU, price/
  currency, lead time, quote date/validity, source reference, protected updates and bounded history.
  Supplier names are batched; VIEWER cannot read these reference prices. Full backend 210 passed,
  final supplier 21 passed, frontend 72 passed, fixed-source full browser regression 22 passed.
  Isolated 0016 build/start/health/metadata/Worker checks passed. Main environment not upgraded;
  stopped isolated containers and retained their volumes after acceptance. See V1_STATUS caveats.

- Company/contact archive now implemented with migration 0015: unified role-aware directory,
  ordinary field/contact maintenance, bounded history, tenant/permission/version/idempotency
  controls and atomic evidence. Backend 190 passed, frontend 68 passed; company browser journey
  passed after fixing success-feedback remounts, PUT forwarding and a test locator. Isolated 0015
  startup/migration/Worker checks passed; main environment unchanged. See V1_STATUS for exact
  separate-run browser evidence and ongoing real-auth/full-system gaps.

- Opportunity lifecycle now implemented under ADR-014/migration 0014: explicit negotiation/loss,
  required reasons and evidence history, CRM-owned inquiry/quotation transitions, concurrency
  guards and list/detail UI. Main environment has not yet been upgraded; see V1_STATUS evidence.

- Procurement cancellation/replacement is now implemented under ADR-013/migration 0013:
  retained receipts, released remaining capacity, linked reapproval drafts, permission/version/
  idempotency guards, atomic evidence and browser controls. See the latest V1_STATUS checkpoint.
  This closes that specific implementation gap, not the other named V1 gaps above.

- `trade-fresh-acceptance`: newly created named volumes and complete root Compose build/start.
  Web/API/PostgreSQL/Redis/MinIO/Worker healthy; worker-beat running; Worker pong; migration
  0011 head and Alembic check clean. Web only exposed at loopback 3300, infrastructure unexposed.
  Production auth session reports unconfigured and `test_bearer=false`; fabricated browser bearer
  rejected with 401. No authentication bypass was used to claim login.
- `trade-recovery-acceptance`: paired cold MinIO volume and PostgreSQL custom-format backup
  restored to empty independent targets. All 38 table fingerprints match, both database-pinned
  file versions retain exact original storage IDs/checksums, all 3 storage versions survive,
  restored Alembic metadata is clean. Backups remain in `backups/20260906-storage-restore`.
- File SHA-256: business.dump `51DE2D6E7E3D5EB060BBF8E34E73CB610BCAFC4634BB0A6327E6D649440A537D`;
  minio.tgz `6FAA5C6ACEDABA6864E566A2D9DA87F9B9BF92F84C361543478E9C1422739690`;
  manifest.json `A2B7BB175AA31DEE749B2470C0CEF684162EF684B1350CCC197DC6FBA7B482BC`.
