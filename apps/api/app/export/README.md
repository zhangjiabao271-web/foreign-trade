# Export and tax refund

Activity query services apply ADR-020 Work content protection before serialization. Unreviewed
summary/details remain confidential without profit.read; stored evidence is unchanged. Human
review uses the subject-scoped Work port with original read authority and exact content/version.
Standalone entity notes and references are not released by a timeline review.

0027 protects original notes/rejection_reason via detached DTOs in list/detail/create/replay,
follow-up and state-command responses. Independent source review requires export.read and
profit.read, exact content/version, confirmation, reason and an idempotency key; it atomically
records activity/audit/outbox without changing business state. Any later row mutation invalidates
release. Final cases remain reviewable without enabling business rewrites. Populated downgrade
is refused and historical text is preserved. Stored case numbers and manual submission receipt
references are business identifiers: visible under original permissions, with cost/profit entry
prohibited under the user's identification-field rule. They are not general-purpose notes.

Manual tracking only. V1 does not submit anything to a customs or tax authority and does not
calculate a statutory refund entitlement. Follow ADR-009 and the implementation guide.

Declarations attach to shipments, refund cases to declarations, with tenant-composite foreign
keys and unique parent associations. Each case snapshots its required document types.
Only AVAILABLE current document versions linked to that case satisfy its checklist.
Commands validate permissions, version, state, evidence and human-provided dates/references,
then atomically write activity, audit and outbox. No generic status patch is permitted.

Amounts use Decimal/four places. A recorded refund cannot exceed the human-entered estimate.
The remaining difference stays visible. Finalized or rejected cases cannot be rewritten.

Case activity endpoints support cursor pagination, scoped to both organization and case.
Case-list cursors require a live organization-owned anchor; missing, foreign and deleted
anchors return 404 INVALID_CURSOR under guide 10/15. This corrects the former 400 status
before V1 release, without changing the error code/details, schema or stored case facts.
ADR-028's error-envelope normalization did not define an exception to tenant lookup rules.
Clearance and refund receipt dates remain in activity and audit payloads.
Follow-up scheduling is an explicit versioned command with a reason. Clearing a follow-up
date removes its deadline, not the underlying case. Finalized/rejected cases cannot reschedule.

Implementation and acceptance are in progress; module presence alone is not acceptance.
