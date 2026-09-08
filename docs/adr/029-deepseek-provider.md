# ADR-029: Explicit DeepSeek V4 Pro provider

Status: Accepted within the user's Sep8 explicit provider choice and paid synthetic acceptance
authorization. Credentials were found by presence-only environment checks, never printed.

Keep the controlled Responses tool loop, PostgreSQL runs, live permissions, bounded retries and
separate content/business approvals. Add an explicit AI_PROVIDER selection (default openai).
DeepSeek uses only https://api.deepseek.com/responses and DEEPSEEK_API_KEY; OpenAI credentials
must never be forwarded there. No arbitrary base URL, model substitution or provider fallback.
The initially allowed DeepSeek model is exactly deepseek-v4-pro.

New DeepSeek runs store deepseek/deepseek-v4-pro in the existing model field, preserving provider
identity without rewriting historical runs. The adapter strips this namespace only on the wire.
Legacy unprefixed models remain OpenAI identities; a worker configured for a different provider
rejects them before network access. This adds no schema or API shape, only an explicit model value.

Official DeepSeek Responses compatibility states parallel_tool_calls is ignored; the application
continues to reject and audit multiple calls, not assume the provider serializes them. It supports
text.format; include/encrypted reasoning are unsupported and omitted for DeepSeek. Returned
reasoning stays only in the bounded in-memory continuation, not durable run output or logs.
Existing output-size, timeout, turn, strict artifact validation and missing-evidence limits remain.
The first live task-draft attempt returned multiple calls and was safely rejected. Prompt version
bounded-intent-v2 explicitly requests at most one tool per response and waiting for its result;
this is guidance only, not a replacement for the application rejection/audit boundary.
Live matrix review found direct fact restatements in the inference list and an order UUID labelled
as an order number. Promptv3 clarifies qualified deductions/recommendations versus factual draft
restatements and permits empty inferences; UUIDs must not be relabelled as human order numbers.
This is model-quality guidance, not deterministic proof that all future outputs obey it.

V3 live PROFIT still occasionally returned parallel calls. Add bounded protocol correction:
all calls in a multiple-call response are denied and audited without executing any; only valid,
distinct call IDs receive a standard error tool-result asking for one call on the next turn.
The existing four-turn cap is unchanged. Malformed/duplicate IDs remain terminal failures.
This is not permission to execute parallel calls or silently select/discard a subset. Exhausting
correction turns fails the run; no automatic additional run, provider or retry budget is created.

Further live review caught a financial inference error: zero contractual deposit was treated as
possibly fully outstanding revenue. Promptv4 explicitly distinguishes agreed deposit from cash/
allocation/balance evidence and marks payment status unknown without such evidence, including
when a bounded timeline lacks payment events. It also discourages redundant successful tool calls.
This does not add financial tools, infer balances in application code, or claim a model guarantee.
Provider cost estimates remain unknown unless explicitly configured; official peak/off-peak/cache
prices must not be represented as an exact bill by a single static tariff.

Only the worker receives the provider secret. API receives provider/model selection for recording
run identity. Web receives neither secret. Local live acceptance uses synthetic evidence only;
paid request permission is not permission for real messaging, banking or government actions.

Sources fetched Sep8:

- https://api-docs.deepseek.com/ (deepseek-v4-pro, currently Pro-0813 alias)
- https://api-docs.deepseek.com/guides/responses_api (stateless Responses compatibility)
- https://api-docs.deepseek.com/quick_start/pricing (variable cache/time tariffs)
- https://developers.openai.com/api/docs/guides/function-calling (call_id/tool continuation)

Acceptance requires configuration/credential isolation and protocol tests, existing permission/
review/runner regressions, container verification and actual provider-backed business drafts.
Adapter code or a standalone model response is not full Phase8 acceptance.
