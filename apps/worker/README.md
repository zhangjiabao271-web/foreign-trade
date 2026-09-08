# Worker

Celery handles retryable side effects but never owns user-visible state. `worker-beat` schedules
the PostgreSQL outbox relay. The relay claims rows with `FOR UPDATE SKIP LOCKED`, commits that
short claim transaction, and only then publishes organization-scoped tasks to Celery.

Guide11.3 reserves default,email,documents,ai,acquisition,exports in Celery's explicit
queue registry, each durable with its own direct exchange/routing key. Existing outbox
publication and Docker consumption deliberately remain on default; declaring names does
not move queued messages,create new business actions or claim dedicated consumers run.
Split routing only with a tested matching consumer rollout. Database facts,tenant context,
receipts,timeouts and retry behavior are unchanged. No dependency or migration is added.

ADR-029 selects an explicit OpenAI or DeepSeek Responses adapter. API and worker must agree on
AI_PROVIDER/model; mismatched stored model identities fail closed without a provider request.
Only worker receives DEEPSEEK_API_KEY; keep it in deployment environment, never source or logs.
There is no automatic provider fallback, expanded tool authority or changed retry policy.

Every business task accepts `TenantTaskContext`. Outbox consumers insert `processed_events` in
the same PostgreSQL transaction as their side effect, so repeated at-least-once delivery is safe.
Failed relay attempts use bounded backoff and become `DEAD`; authorized API commands can replay
them after an operator supplies a reason.

Broker publication alone is not delivery acceptance. Every minute a bounded recovery scan
requeues up to 50 PUBLISHED events older than 15 minutes without the intended
`worker.<event_type>` PostgreSQL receipt. In-flight duplicates remain safe through consumer
idempotency. Five unsuccessful publications move the event to DEAD for authorized replay.
Normal consumers use late acknowledgement, worker-loss redelivery, finite retries and
120/150-second soft/hard limits. Relay failure backoff includes jitter. No new schema is needed.

ADR-019 lifecycle observers emit safe JSON task outcomes, validated context IDs and duration,
never task arguments, results or raw exception messages. Default task limits are 30/45 seconds;
the explicit longer business task limits remain unchanged. A bounded process-local start map
is diagnostic only. Hard-killed tasks may lack a finish log; durable PostgreSQL status/receipts
remain authoritative and recovery remains responsible for redelivery.

Container commands include `--quiet` to suppress Celery's direct-print startup banner, which
would otherwise bypass the JSON formatter. Warning capture is installed before worker startup.
API containers load `apps/api/logging.json` before serving; raw Uvicorn access/startup messages
are not a safe alternative to the structured application request events. Native QueuePool
overflow may be negative while its configured pool has not yet filled; it is not a failure count.
