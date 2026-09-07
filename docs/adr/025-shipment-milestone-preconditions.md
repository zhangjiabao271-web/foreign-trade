# ADR-025: Shipment milestone preconditions

Status: Accepted for authorized unreleased V1 implementation, 2026-09-07.

## Decision

All seven milestones require the displayed shipment expected_version and Idempotency-Key at
HTTP/service boundaries. ShipmentResponse exposes its existing row counter. Missing guards fail;
this explicitly replaces the unreleased unguarded protocol, requiring coordinated owned-caller
updates before deployment. Existing counters and receipt storage suffice; no migration/dependency.

Acquire scoped parent sales orders in ID order, then shipment, then the action-scoped key. The
receipt binds shipment ID and validated request, including the booking reference. Matching replay
returns the original live shipment's current facts and current document gaps even after subsequent
milestones or parent finalization. It rechecks authority and never repeats timestamps or evidence.

Fresh decisions require matching version, complete live source/parent mappings and executing,
ready-to-ship or shipped parents; finalized parents reject. Recheck persisted shipment capacity
under parent locks. Existing milestone state/document rules remain. Already-at-target guarded
no-ops retain receipts, but a different booking reference conflicts instead of silently succeeding
or replacing the original booking. New requests cannot reopen completed business facts.

State, independent timestamps, Sales-owned order progress, activity/audit/outbox and receipt share
one transaction. Current AVAILABLE/pinned document rules remain authoritative for new restricted
transitions. Recovery of a committed receipt reports present gaps without retroactively rerunning
its old prerequisite checks. No logistics message or external booking occurs.

The UI freezes the booking form's opening version, sends displayed counters for other actions,
retains original request variables for explicit recovery after refetch, and discards local retry
identity when shipment/session changes. No persisted browser key or frontend authority is added.

## Acceptance

Cover seven actions, all roles, mandatory/stale input, identical/conflicting/no-op/later replay,
tenant/deletion, parent finalization, current document gaps, atomic evidence failures and competing
key/version/parent transactions. Verify generated client, owned UI, browser lost-response recovery
and isolated build/runtime. See V1_STATUS for actual evidence, not an assumed release certificate.
