# ADR-021: Bind quotation decisions to the reviewed version

Status: Accepted within the authorized unreleased V1 implementation scope, 2026-09-06.
Implementation in verification; this decision is not acceptance evidence.

## Problem

The original submit/approve/send/accept/reject/expire handlers resolve whichever version is
current when the request executes. Row locks protect state transitions, but cannot establish
that this is the version the human saw. A stale page can therefore act on a later revision.
Status-only retry handling cannot reliably recover an uncertain result after later transitions.

## Decision and compatibility

These six commands will require an expected_version_id, expected_version row counter and
Idempotency-Key at both HTTP and application command boundaries. There will be no unguarded
fallback that silently chooses the current version. Missing guards return validation failure;
stale new requests return VERSION_CONFLICT without business/evidence/key writes. Command keys
are tenant- and action-scoped; different input under an existing key returns IDEMPOTENCY_CONFLICT.

This is an explicit breaking change to the unreleased V1 command contract, not a claim of
backward compatibility. Update the generated OpenAPI client, owned UI, fixture utilities and
direct test/script callers together. Main deployed containers must not be silently upgraded.
If external consumers are discovered, deployment requires a coordinated consumer upgrade.
Business states, permissions and accepted commercial snapshots do not change. No schema
migration is necessary: existing row counters and durable idempotency records suffice.

## Transaction and replay

Retain quotation-before-current-version locking, and quotation-before-opportunity locking for
acceptance. Persist the command receipt in the same transaction as state, activity, audit and
outbox. Replay still checks current organization, active quotation and action permission, then
returns the originally affected live version through the current role's protected projection.
It must not execute the operation on a newer current version, repeat evidence, or release costs
or text. Subsequent business changes may be reflected in that original version's current state.
Deleted/foreign resources cannot be recovered. Cost authority remains independent of replay.

## User experience and acceptance

The owned page sends the exact displayed version identity and counter. Preserve the submitted
snapshot/key for an explicit unchanged retry after a lost response; background refresh must not
rewrite that retry into a command against a new version. A new decision from refreshed content
uses its own preconditions. Organization/session changes discard local operation state.

Verify all six commands for omitted/stale guards, valid transitions, identical and conflicting
replay, later revisions, live permissions/tenant/deletion checks, concurrent decisions and
activity/audit/outbox rollback. Preserve quotation validity, opportunity loss/win, immutable
snapshot and confidentiality regressions. Browser evidence must include a server-committed lost
response and a stale-view rejection, alongside the complete commercial journey. Build/start and
client drift checks remain required. Existing green tests predate this mandatory guard contract.
