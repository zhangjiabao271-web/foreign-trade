# ADR-011: Bounded, audited Copilot with human task approval

Status: Accepted within the approved Phase 8 implementation scope.

The first Copilot uses explicit intents (search, timeline summary, profit explanation,
email draft, follow-up task draft) and bounded application tools. No arbitrary SQL, shell,
external URL, database credential, core state-changing tool or messaging tool is exposed.
Organization and actor are injected from authenticated context, never model arguments.

Runs are PostgreSQL jobs dispatched through outbox. Provider requests occur outside database
transactions. Every tool invocation revalidates current membership and explicit domain
permissions; arguments reject extra keys. Results are bounded, reference-backed snapshots.
Runs and tool calls record safe summaries, references, model/prompt version, token usage,
nullable configured cost estimates and stable errors. Raw user prompts, tokens, provider
errors and business document bodies are not copied to logs or outbox.

The provider receives a structured intent and only allowlisted tool outputs. Untrusted text
is data, never authority. Responses use strict function schemas and bounded turns/output.
OpenAI is configured with environment credentials and a model name; no automatic fallback
pretends to be a live model. Without configuration, provider execution fails closed with a
clear status. Local deterministic provider fixtures test application boundaries only.

AI artifacts distinguish source facts, model inferences and drafts. Reads require the run's
recorded permission set as well as current organization membership, so privilege removal
cannot reveal previously generated sensitive results. Personal runs stay private to their
creator except explicitly submitted approval snapshots.

The initial executable approval is an order follow-up task, not a commercial/financial
state transition. A human requests approval for an immutable draft, then an authorized human
approves or rejects with an optimistic version and reason. Approval plus Work-owned task
creation plus audit/activity/outbox commit atomically. Repeated approval cannot duplicate tasks.
No automatic mail sending or core commercial state change is implied by approving a draft.

Official implementation sources, fetched 2026-09-06:

- https://developers.openai.com/api/docs/guides/function-calling
  (`.md` endpoint supplies readable source): Responses function_call, call_id,
  function_call_output; strict schemas; preserve returned reasoning items in the tool loop;
  parallel_tool_calls=false for a serial bounded loop.

This decision narrows initial execution authority without relaxing guide section 13.
Live provider credentials/login and production deployment acceptance are distinct from tests.
