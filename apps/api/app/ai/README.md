# Controlled Copilot

Follow guide section 13 and ADR-011. PostgreSQL owns runs, tool-call receipts and approvals.
ADR-029 adds explicit AI_PROVIDER=deepseek and deepseek-v4-pro via the official Responses endpoint.
Run model identities use deepseek/deepseek-v4-pro; worker provider mismatches fail before network.
Only DEEPSEEK_API_KEY is sent to DeepSeek, with no fallback or configurable destination. Provider
parallel-call disabling is not trusted: the existing runner still rejects/audits multiple calls.
Encrypted reasoning include is omitted for this provider; all other application limits remain.
For valid distinct IDs, denied parallel calls receive bounded error feedback; no tool in that
response executes. Correction consumes the same four-turn allowance. Invalid or repeated IDs fail
immediately. Promptv3 separates factual draft restatements from qualified inference/recommendations
and distinguishes order UUIDs from human order numbers. Model compliance still needs review.
Sep8 live opt-in synthetic TASK_DRAFT passed with the real adapter/runner: source tool evidence,
unchanged order state, private sales projection and cross-owner/tenant404 were checked. Promptv2
requests serial tools after a real multiple-call rejection; enforcement remains application-owned.
Other intents, live browser review and deployed worker acceptance remain open. The optional
test_deepseek_live_acceptance.py never calls a paid provider without explicit environment opt-in.

Latest Sep8 supplement: promptv4 five-intent real synthetic matrix passed, including explicit
unknown payment/balance when only contractual deposit evidence is supplied. Actual manager
browser/queue/provider summary passed onv2. See V1_STATUS for finalv4 runtime and remaining
review UI checks; historical failed matrix runs are preserved and not erased by a later pass.
Tools call permission-checked application services; model arguments never carry trusted
organization/actor context. There are no SQL, shell, outbound-message or core-state tools.

Worker provider calls must run outside DB transactions. Resolve live membership at every
tool boundary. Keep outputs bounded and auditable; persist references and safe summaries,
not raw credentials or prompts. Tests use an explicit fake provider, never silent fallback.

Malformed or multiple tool requests are denied with individual hash-only receipts. Transient
provider unavailability returns the PostgreSQL run/job to PENDING before worker retry, bounded
by three execution attempts. Configuration/authority/argument failures are terminal, not retries.
An active lease prevents duplicate execution; an expired lease permits bounded recovery.

Order task approval executes through a Work-owned transactional port. Approval is human,
version checked and atomic with its task, activity, audit and outbox. All remaining core
business actions stay in their existing human-operated command workflows.

Implementation and acceptance are in progress. Module presence is not acceptance.

ADR-026/0033 adds creator-submitted content disclosure, separate from task execution approval.
Only submitted candidate artifacts are visible to same-organization ai.read + profit.read
reviewers with the relevant domain read right. Private run/tool endpoints remain owner-only.
Lower-privilege creators receive no original input/output/tool prose or provider cost; only
the latest approved exact candidate artifact is released. Structured facts/references and
approval copies/reasons do not inherit release. Unknown provider tool names are also redacted.
Revisions append pending candidates; original runs and prior candidates are preserved. Run or
candidate changes invalidate release. Submit/revise/decide lock the run and use durable keys
and atomic evidence. A low-privilege task request must name the displayed released candidate
ID/version; content review cannot create tasks or grant finance ai.approve.
Candidate queue pagination computes current revision before applying the cursor so historical
pages never reopen an old release. Queue fetch is one business SELECT; run projections batch
their latest disclosure lookup. See docs/acceptance/AI_DISCLOSURE.md for actual evidence.
