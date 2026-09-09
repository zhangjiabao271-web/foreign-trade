# V1 final reconciliation working sheet

Checkpoint:2026-09-09. This is the current requirement-to-evidence map, not a release certificate.
The implementation guide, accepted ADRs and explicit user decisions remain authoritative.
Historical acceptance files retain their chronology; old pending-login/upload/recovery notes
must not trigger those actions again. No additional production scope is silently substituted.

## Current version boundary

- Remote application/test source:3cda32a41b5c3bd97a538611514b082fb1f4aefd.
- Seventh CI34326750634 completed successfully: quality102385661574 and smoke102385661303.
- Full raw quality logs confirm Web267/API-Worker2236/browser32 passed, six expected skips,
  one backend deprecation warning, successful generation/drift/static checks and19-page build.
  Skip reasons match the independently inspected paid-provider/Windows guards below.
- Sixth CI34322866363 atc186135 is fully successful, with archived quality and smoke evidence.
- Local ce93046 adds deployed API selection/script and documentation, not application changes.
- The actual API includes both Documents completion and Export cursor fixes. Source hashes,
  exact image, health200 and preserved configuration/data are in FULL_GUIDE_AUDIT's newest
  deployment entry. Ten Compose layers are required. Older deployment scripts must not rerun.
- Worker/Web remain the previously verified owner-port/session-presence versions. No actual
  model task, financial record, document or retained restore was recreated in the final audit.

## Current retained runtime evidence check

Sep9 read-only PostgreSQL transaction, scoped to the recorded organization and exact existing
sample IDs, confirmed the commercial order COMPLETED with selling1250/cost snapshot734.10,
shipment DELIVERED, customs CLEARED and refund REFUNDED with estimate100/received90. The
separate AI order's whole-row fingerprint still equals its pre-approval baseline. Its approval
is APPROVED with the original manager and exact task ID; that task is OPEN, assigned to the
same manager and linked to the correct order. The read ended with ROLLBACK and changed no facts.

The accepted BOL database version remains AVAILABLE,644 bytes, pinned and released. The exact
previously downloaded Windows file still exists and was independently rehashed:
`1fc47705160be7ad9de6e9a9b84b663c7326a2169330e60a36813d8bccffa161`, matching the database.
This is retained-byte verification, not a new download or another role's browser demonstration.

Joint recovery documentation was checked for actual three-database/table/role/object results,
restored real Logto logins and return-to-source. Its encrypted package inventory remains present;
no package was decrypted, overwritten or restored again. Inventory presence alone is not used
as recovery proof: the prior actual recovery and exact comparison results retain that role.
The explicit CurrentUser/no-cross-machine limits are unchanged.

Seventh fresh-smoke raw logs were inspected:0035head, Web/API ready, PostgreSQL/Redis/MinIO
dependencies true and Worker pong/one node online. Quality is still live; smoke is not final CI.

## Named foundation deliverables

Task003's verifier/context/membership/test issuer/repository/job obligations map to the specific
source and72 foundation cases in TASK003_ACCEPTANCE. Task004's UoW/domain event, transactional
records, SKIP LOCKED, publication, receipt deduplication and replay map to25 overlapping cases
in TASK004_ACCEPTANCE. The latest Platform49-case run independently revisits public tenant
entries, direct query guards, replay concurrency/rollback and operational metrics.

Task005's complete106-file type traversal,183 operation IDs, actual copied-Pydantic mutation
negative probe, generated Lead query and shared errors are documented in TASK005_ACCEPTANCE.
The sixth remote CI independently passed clean generation and all drift probes. Earlier lines
in that historical file saying remote execution or whole-Web type inspection is pending are
superseded by their later evidence; they are not additional implementation tasks.

Task006's source/migration/API/browser conversion, role unification, conversion races, search
and filter controls have the named tests and actual reports in TASK006_ACCEPTANCE. The broader
Companies/CRM paths were subsequently reconciled in FULL_GUIDE_AUDIT, not inferred from this
single foundational journey.

## Business command reconciliation

The following records distinguish finite state/role tests from natural business journeys.
Seeded states isolate guards in disposable databases; they are not fabricated real orders.

| Family                       | Direct rule evidence inspected                                                                                                                                                                                                                                   | Execution correspondence                                                                                                                    |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Quotation decisions          | test_quotation_decision_states defines independent allowed/target maps for six decisions across all version states; unapproved send separately denied. test_quotation_decision_roles exercises all six roles and denied direct services.                         | Included in sixth CI; current source unchanged by later supplements.                                                                        |
| Customer-review/revision     | test_quotation_review_revision_matrix exercises both actions across all states and six roles, retained original versions, exact evidence and replay. Creation/revision/state command tests cover keys, stale versions, concurrent winners and failed evidence.   | Sixth CI; foreign-manager eight-command supplement also included there.                                                                     |
| Sales-order ownership        | Creation and confirmation have dedicated keys/versions/roles/rollback/race tests; all eight confirmation states are in test_sales_foreign_commands. Settlement and shipping advance through Sales-owned ports, not generic status writes.                        | Sixth CI for original/order supplements; subsequent customer Finance tests require seventh CI.                                              |
| Customer receivables/payment | test_finance_rules checks all five derived states with explicit business day and Decimal amounts. Finance vertical slice covers deposit/balance, reversal, over-allocation, concurrent payment/receivable races, unique numbers and protected command responses. | Latest customer Finance40-case report independently parsed:0 failures/errors/skips.                                                         |
| Order completion             | Finance vertical slice proves stale/not-shipped/unauthorized rejection; naturally delivered orders remain blocked by unpaid amounts or tasks; paid and explicitly waived cases complete with evidence and no-write replay. Waiver retains unpaid facts.          | Included in the customer40-case run; completion/refresh concurrency and lock-order tests are part of that combination.                      |
| Customer command rollback    | test_customer_finance_atomicity covers generate/refresh/reverse/complete at each activity/audit/outbox after-insert failure, exact selected-row rollback and subsequent recovery/replay. Payment create/allocation have separate original evidence tests.        | 12-case report independently parsed:0 failures/errors/skips; seventh CI pending.                                                            |
| Supplier settlement          | Existing settlement and purchase-finance tests cover posting, payment, allocation, reversal, voiding, partial/full amounts, currencies, overpayment, concurrent operations and three evidence failures; cancellation/amendment retain debt.                      | 34-case supplier report independently parsed:0 failures/errors/skips; seventh CI pending.                                                   |
| Procurement/Shipment         | Independent status/role/tenant matrices and three-record failures are reconciled in FULL_GUIDE_AUDIT; natural receiving, shipping, delivery and order progress have separate journeys. Archived/foreign forwarder correction is deployed.                        | Sixth CI includes those supplements and forwarder fix.                                                                                      |
| Export                       | Independent customs5/refund6 transition maps across6/7 states, all six roles, foreign/stale rejection and follow-up states; source review is independent. Both creations now include three evidence-failure cases.                                               | 66-case correction report and10-case paths/creation report independently parsed, both clean; overlapping, not additive. Seventh CI pending. |
| Work/Contracts/Expenses      | Their finite route/command/source-review matrices and transactional rollback are reconciled in FULL_GUIDE_AUDIT; task execution and text release remain separate.                                                                                                | Sixth CI plus recorded targeted reports; no new production action required.                                                                 |
| AI                           | Four tools/five intents have separate bounded authority evidence. Fourteen HTTP operations plus all cursor variants and direct services reject foreign MANAGER; private runs remain private despite review authority.                                            | 77-case AI report independently parsed clean. Real DeepSeek draft/review/execution evidence remains separate in AI_DISCLOSURE.              |

## Cross-cutting guide gates

| Guide requirement                                         | Authoritative evidence and remaining release boundary                                                                                                                                                                                                            |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0/17 quality and disciplined changes                      | Latest exact-SHA CI, explicit staged scans and preserved worktree; current seventh run must finish.                                                                                                                                                              |
| 1/2 first profitable order and actionable queues          | Real synthetic commercial journey and funding estimate ADR027; GUIDE_18_GATES and REAL_IDENTITY. Eight populated queues/query-size checks have direct evidence.                                                                                                  |
| 3/10/15.1 roles and tenant isolation                      | Task003 plus per-module entry/repository maps in FULL_GUIDE_AUDIT; anonymous route sweep is separate from valid-user tenant checks. All newly added domain tests must be included in seventh CI.                                                                 |
| 4 database fields/relationships/amounts                   | test_database_acceptance_invariants inspects actual PostgreSQL types, tenant unique/FK scope and validated/enabled constraints; explicit polymorphic/correlation exceptions require their application tests. No Float columns. Audit DELETE refusal is asserted. |
| 5/11/15.2–8 business state, atomicity, money and delivery | Command map above and prior module maps; real PostgreSQL concurrency plus retained actual Redis/Worker recovery evidence, not only dispatcher substitutes.                                                                                                       |
| 6–8 architecture/ownership/license                        | MODULE_OWNERSHIP and ADR030–034 record corrected owner ports; full regression/deployment evidence supersedes historical source-only findings. License review is distinct from runtime behavior.                                                                  |
| 9/15.11 generated contract                                | TASK005 and exact current CI; Export404 correction retains code/details and generated schema and is explicitly documented as a pre-release correction.                                                                                                           |
| 12/15.9 attachments                                       | Version/checksum/MIME/tenant/checklist/review tests plus644-byte real sales download and original-version recovery. Completion fix installed and hash verified. Production malware engine is explicitly not provided.                                            |
| 13 AI control                                             | AI_DISCLOSURE live synthetic evidence plus scripted tool, HTTP, role, retry and atomicity suites. No arbitrary SQL/core-state/outbound tools; content approval cannot authorize task execution.                                                                  |
| 14/15.10/12 operations, secrets, migration and restore    | Platform monitoring/white-list logs; original CurrentUser encrypted joint recovery and0035 copy migration records. Local deployment preserves settings without printing secrets.                                                                                 |
| 16 Phase0–8 and18.1–8 demonstration                       | Concrete domain artifacts, generated client, main browser journey in three currencies and separate real Logto sales/manager journey; full local V1 scope retained.                                                                                               |
| 18.9–10 recovery and clean startup                        | Retained recovery evidence and sixth complete CI; seventh fresh smoke currently success, latest quality completion still needed.                                                                                                                                 |
| 18 performance                                            | GUIDE_18_GATES identifies24 measured operations, populated datasets and exact samples. Initial local benchmarks, not all-endpoint production SLO guarantees.                                                                                                     |
| 19–21 named tasks and decisions                           | Foundation map above and ADR008–034/user decisions; production hosting/channel/scanning and cross-machine disaster recovery remain separately configured, not concealed local failures.                                                                          |

## Accepted ADR and guarded-browser reconciliation

The remaining ADR023/024/025 text was read in full; its acceptance obligations do not require
another actual order, supplier message or shipment. The current browser source
`apps/web/e2e/quotation-lifecycle.spec.ts` was inspected for committed-response-loss behavior,
not merely test names: it executes the real request with route.fetch, checks successful status,
then aborts delivery to the page. Recovery checks the original request body/key and resource ID.
Order creation additionally retains the deposit input; stale quotation/order/purchase views
explicitly reject VERSION_CONFLICT. The same journey exercises procurement approve/send/confirm
and each of book/ready/enter-customs/depart/start-transit/arrive/deliver through recovery helpers.
Quotation submission is its representative guarded-decision browser loss case; all six quotation
decisions have separate backend/owned-UI coverage, not six claimed browser loss demonstrations.
These assertions were included in the sixth green32-browser run; the seventh execution remains
pending. No browser or real-role journey was rerun during this source reconciliation.

ADR008-019 obligations map to the finance/locking, immutable file, Copilot, real identity,
procurement amendment, CRM, contract, expense, supplier settlement, membership and operations
records above and in FULL_GUIDE_AUDIT. ADR020/026 retain separate cost/text confidentiality,
candidate review and execution approval evidence; ADR027's estimate is not a cash-flow forecast.
ADR021-025 caller guards and rollout are supported by their backend/form/browser records and
subsequent deployed-source evidence, superseding their historical not-yet-deployed checkpoints.
ADR028 preserves safe error envelopes; ADR029 has separate live five-intent and approved-task
evidence; ADR030-034 owner-port changes retain their transaction and deployed regression maps.
This finite review found no additional local-scope ADR acceptance action beyond the final remote
checks and upload below. Production-only configuration remains explicitly outside this result.

The six Linux CI skips are identified in source: five parameterized real-provider intents in
`test_deepseek_live_acceptance.py` require ALLOW_PAID_DEEPSEEK_ACCEPTANCE=1, and the one
`test_e2e_process_ownership.py` case requires Windows. The paid cases have a separately recorded
real five-intent run (session90632:5 passed,66.89s), not CI coverage. The retained Sep9 Windows
JUnit report is separate platform-specific evidence, not an additional Linux pass. Final remote
logs must still confirm the observed skip total; no skipped case is relabeled as a CI pass.

## Remaining release actions

1. Seventh terminal quality logs, actual skip reasons and browser/build results are now reconciled.
   The earlier still-live wording above is retained checkpoint history, superseded by this result.
2. Upload the subsequent deployment record/configuration and verify exact remote synchronization;
   application/test/dependency/CI/root-Compose differences against seventh SHA were checked empty.
3. Inspect any resulting latest upload checks before final handoff. No further application changes,
   repeated login, restore, paid run or business approval are required by the completed finite map.
   Local V1 acceptance includes simulated external business steps and CurrentUser joint recovery;
   production hosting/scanning/channels and cross-machine recovery are not certified by this map.
