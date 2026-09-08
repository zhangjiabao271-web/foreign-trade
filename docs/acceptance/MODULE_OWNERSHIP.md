# Module ownership audit checkpoint

2026-09-09. Guide8 requires cross-module writes through owner application services/public ports.
This document records inspected write bodies, not a complete static-analysis certificate.
Read-only foreign-model imports are not, by themselves, ownership violations.

## Sep9 dynamic-write follow-up

Read-only search for status/amount/total/version/progress/attempt/reference assignments was
followed by inspection of dynamic setattr and SQLAlchemy values write bodies. The inspected
Catalog supplier fields target ProductSupplierLink; Companies archive fields target its own
Company/Contact; Fulfillment transition fields target Shipment; Sales transition timestamps
target QuotationVersion; Procurement transition timestamps target PurchaseOrder. These are
owner-local writes, not further foreign-ORM findings. This classification does not prove every
request-field whitelist or every state/permission path correct.

Platform outbox/numbering full sources were read: bulk recovery updates OutboxEvent,consumer
receipt insert targets ProcessedEvent,generic job handler updates AsyncJob,and numbering
upserts DocumentSequence. Companies conversion_repository full source upserts Company/Role.
Identity add_member inserts its own global User mapping with conflict-do-nothing rather than
updating an existing global identity; membership remains explicitly organization-scoped.
Those SQLAlchemy writes are owner-local. Relay's deliberate infrastructure-wide claims are
not a tenant business repository; message-specific finalization checks organization/event/lock.
No new application change resulted. This bounded search/body review is not whole-program
alias/dataflow proof and does not replace the broader guide invariant matrix.

Latest runtime checkpoint: owner-ports API/Worker/beat are now deployed after full1292pass and
browser32pass. Exact environments,22commercial/file fingerprints and four other container IDs
matched; API live/ready200 and Worker Redis inspect pong passed. Earlier not-deployed statements
are historical. See V1_STATUS for full identities and limits; this does not close broader audit.

## Corrected and separately verified

- Sales quotation creation now calls Inquiries-owned quotation_progress; ADR030 records the
  CLOSED-source refusal. Source, related184tests, browser32 and API deployment are recorded in
  V1_STATUS. No additional approval or source reclassification is implied by this audit.
- Finance allocation/reversal delegates order mutations to Sales OrderSettlementPort. Both
  originating permissions are now rechecked at that port. Direct and normal Finance18tests,
  strict213-file types and actual deployed pre-order-access denial probes passed. The caller
  still validates monetary facts and holds the order lock; the port is not a standalone payment API.
- Fulfillment milestone transitions delegate order updates to Sales refresh_shipping_progress;
  its body checks shipment.transition and reads persisted quantities through Fulfillment's port.
  Existing parent-after-insert fault tests cover complete transaction rollback for one/two orders.

## Confirmed remaining write boundaries

Superseding ADR-034 checkpoint2026-09-09: item4 below is corrected in source through Work
records, preserving all38 original payloads across32files and separate null-actor scan origin.
Targeted54 tests passed (JUnit rechecked); current-source full regression93777 is still live.
API candidate isolated actual uvicorn live200 and Worker isolated registry/eager health passed.
The latter does not prove broker consumption. No deployment yet. All four original findings
below are retained as history, not current uncorrected constructor claims; broader ownership
audit, full current-source results and coordinated deployed verification remain open.

Superseding ADR-032/033 checkpoint2026-09-09: items2 and3 below are corrected in source.
Sales confirmation calls Work, which reads immutable Sales-owned tenant/state-checked source;
AI/Documents use Platform domain job ports without foreign ORM writes. The trusted worker
failure recorder remains usable after actor permission loss. Confirmation27, jobs62 and extra
integrated atomicity4 tests passed in separate runs. Strictmypy218/client drift passed; combined
candidate real uvicorn live200 in network-none/no-volume container. Not deployed. Item4 remains
open; after it, current-source full regression and coordinated API/Worker deployment are required.

Superseding checkpoint2026-09-09: item1 below is now corrected in source by ADR-031 and
Companies lead_conversion/conversion_repository. Current-source CRM/Companies72tests passed,
strictmypy215files and actual client drift passed. Candidate network-none uvicorn live200;
not deployed. Original findings below remain audit history; items2–4 remain open. See V1_STATUS.

1. CRM LeadCommandService.convert, services.py135–200, constructs Company and Contact and calls
   CRM ConversionRepository to INSERT Companies-owned Company/CompanyRole. The full CRM service,
   repository and both module READMEs were read. The repository's contact/opportunity reads are
   separate from this write finding. No Companies-owned conversion write port is used.
   A correction must move company resolution/customer-role insertion/contact creation behind a
   Companies-owned transaction port, preserving normalized-name conflict arbitration, inactive
   role refusal, each lead's separate contact/opportunity, originating lead.convert authority,
   lead-first locking, replay and the original single transaction/evidence stream.
   test_crm_acceptance_matrix monkeypatches ConversionRepository.find_company/find_role to force
   concurrency; update those fault points to the actual owner rather than dropping the races.

2. SalesOrderCommandService.confirm, order_services.py321 onward, directly constructs Work Task
   for PROCUREMENT_PREPARATION. It sets HIGH priority, two-day due time and order
   details inside the confirmation transaction. Work owns Task; its existing approved_tasks port
   is specific to AI approval and must not be reused with a fabricated approval ID. A narrow
   Work-owned procurement-preparation port should preserve exact fields and confirmation atomicity.

3. AiCommandService.create directly constructs Platform AsyncJob then assigns result_reference;
   DocumentCommandService.complete constructs the DOCUMENT_SCAN job directly. Bodies were read;
   no Platform-owned job-creation port is called in these paths. The complete AiRunner and
   document mark_document_available handler were subsequently read with Platform/AI/Documents
   READMEs, ADR011 and Platform commands/services/repositories. AiRunner directly sets job
   RUNNING/attempt_count and later status/progress/error_code under run-then-job locks; its
   _job query scopes organization and ID. Document completion directly sets job SUCCEEDED,
   progress100 and result_reference under document-version-then-job locks. A correction must
   cover these lifecycle writes too, not just constructors. Existing PlatformCommandService
   creates a different generic job with its own UoW and async_job.created event: invoking it here
   would split atomicity/change dispatch. Do not use it as a drop-in wrapper or duplicate events.
   AI permission loss still needs to persist a terminal job/run failure, so requiring a user's
   now-removed AI write permission in an internal failure recorder would be incorrect. Separate
   authorized request creation from trusted tenant-bound worker lifecycle reporting.

4. Several domains directly construct Work Activity, whereas audit/outbox use Platform-owned
   recorders. Those activity constructors are visible in the source inventory, but their exact
   evidence contracts and any accepted cross-cutting exception require reconciliation before
   declaring a complete ownership pass. Do not change event types or release historical text.
   Work's existing approved_tasks helper only serves AI task creation; no general activity
   recorder exists in the inspected Work model/services/README. The document worker uses a null
   actor with the event correlation ID, unlike user-command records. Any owner recorder must
   preserve that distinction, original summaries/details/timestamps, caller flush ordering and
   default-confidential metadata. Platform AuditRecorder/OutboxRecorder provide a noncommitting
   owner-recording pattern; activity recording must not recursively audit itself.

## Execution boundary

Latest superseding result: current-source93777 completed1292passed,5paid-skipped,1warning,
exit0 in2084.88s; JUnit independently confirms0failures/0errors. It includes ADR031-034.
Earlier live references are historical. Coordinated deployment and broader ownership audit
remain separate obligations; this full test pass is not proof of every architectural property.

Current-source browser40431 also terminated exit0:32passed/4.1minutes. Independent cleanup
confirmed no test database, no3100/8010listeners and no fixture/owned-process receipts.
Scripted provider only; candidate images still not deployed.

Superseding result: session31821 finished1253passed,5paid-skipped andone Windows temporary-root
setup error; the affected ownership test separately passed in a fresh workspace basetemp.
See V1_STATUS. The run is terminal. This does not close the write boundaries listed above.

Full regression session31821 used the settlement-permission checkpoint. No application or test
source was modified during this inspection. The findings above prevent treating that checkpoint
as final V1 acceptance. Preserve its results; subsequent owner-port corrections need their own
targeted and final-current verification.
This audit does not authorize external messages, model calls, data migration or new user roles.
