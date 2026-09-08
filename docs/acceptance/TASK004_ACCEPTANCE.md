# Task004 foundation acceptance mapping

## Consolidated report revalidation (2026-09-09)

Independently parsed the completed `tmp/full-reconciled-20260909.xml`: platform_transactions16
and worker tasks9, total25, with zero failures/errors/skips in these groups. These are included
in the latest1476-pass backend/worker run, not a new execution or an addition to that total.
The worker9 cases are shared with Task003's evidence. Platform README reread retains the
distinction between a successful replay request and successful consumption, and between
adapter tests and a real broker recovery exercise. No event was replayed in this check.

Checkpoint 2026-09-09. Scope: the named Task004 transaction/outbox foundation,
not a complete V1 release certificate. This review read the implementation and test
bodies and extracted the existing `tmp/full-owner-20260909.xml` report:
`apps.api.tests.test_platform_transactions` 16 cases and
`apps.worker.tests.test_tasks` 9 cases; 25 total, no failure/error/skip.
Report extraction is not a new test run.

| Task004 obligation                     | Implementation and direct acceptance evidence                                                                                                                                                                                                                                                                                                                                                                       |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reusable Unit of Work and domain event | `core/unit_of_work.py` owns an explicit session, opt-in commit, otherwise rollback and close. `platform/records.py` defines a frozen DomainEvent; both recorders stage records in the caller's session without committing.                                                                                                                                                                                          |
| Same-transaction business/audit/outbox | `PlatformCommandService.create_job` writes all three and commits only after the last stage. `test_command_atomically_writes_business_audit_and_outbox` checks persisted records and matching request/correlation IDs.                                                                                                                                                                                               |
| Rollback leaves no event               | `test_failure_injection_rolls_back_every_record` independently injects failure after business, audit and outbox flush; each case asserts zero jobs, audits and events. This foundation example does not replace later domain activity rollback tests.                                                                                                                                                               |
| Worker cannot see events before commit | `test_relay_cannot_claim_uncommitted_event` flushes an event in an open transaction, then runs the relay through a separate session; claimed count and dispatcher messages are both zero.                                                                                                                                                                                                                           |
| SKIP LOCKED and two concurrent relays  | `OutboxRelay.claim_batch` orders/limits a `FOR UPDATE SKIP LOCKED` query and commits the short claim transaction before publication. `test_two_relays_do_not_claim_the_same_event` runs two threads over 12 committed events and checks exact IDs, total claims and no duplicate publication.                                                                                                                       |
| Celery publication                     | `worker/outbox.py` maps event type to the registered task and explicitly forwards organization/correlation context on the default queue. Worker dispatcher tests assert exact task/kwargs/queue. These tests intercept send_task, not a live broker. `worker/tasks.py` connects the actual relay and consumer implementations.                                                                                      |
| Idempotent consumer example            | `IdempotentEventConsumer` inserts the organization/event/consumer receipt using conflict-do-nothing and runs the handler in that same transaction. `test_duplicate_delivery_applies_side_effect_once` verifies first true, second false, counter one and receipt one. The real async-job example writes a tenant-scoped event reference.                                                                            |
| Dead-letter/replay management command  | Failed dispatch reaches DEAD at the configured attempt limit. `OutboxAdminService.replay` checks permission, reason, tenant, DEAD status and optional displayed version under a row lock, then resets the original event and records audit atomically. Tests cover success, concurrent single winner, forbidden/foreign/stale/blank requests and audit-failure rollback. Requeue is not proof of execution success. |
| Bounded and safe dead listing          | The service requires outbox.read. `test_dead_list_is_bounded_tenant_scoped_and_redacts_errors` checks paging, foreign-organization empty results and allowlisted error serialization.                                                                                                                                                                                                                               |
| Recovery and delayed duplicates        | Three additional tests check intended-consumer receipt matching, age/attempt bounds, two concurrent bounded recovery scans, and simulated lost publication followed by a late duplicate with one side effect. RecordingDispatcher models loss; it is not Redis failure injection.                                                                                                                                   |

The four explicitly named Task004 acceptance outcomes have direct real-PostgreSQL
test evidence. Celery wiring has source and adapter-test evidence. Historical actual
Redis/Worker recovery and retained database receipt checks are recorded separately in
`GUIDE_18_GATES.md`, section 18.9; this review did not restart a broker, inspect that
retained database again, replay an event or alter live business data. Current deployment
health alone must not be used as proof of failure recovery. Management UI acceptance and
all later business consumers remain subject to their own V1 evidence, not this foundation
mapping. Real AI task acceptance still awaits the user's exact-data disclosure consent.
