# Orders and procurement workspace

Order history now mounts independently of OrderFinance and uses the cursor activity-history
endpoint through CommercialTimeline, reaching older records beyond100. Original order.read and
content-review restrictions remain; a finance fetch failure no longer hides the whole timeline.

Order navigation explicitly loads50 records per cursor page and shows an accumulated loaded
count, not a global total. Shared infinite-query pages deduplicate IDs and remain inside the
identity/organization QueryClient boundary. Failed subsequent pages retain loaded records;
retry keeps the cursor, while explicit restart resets pagination. Existing invalidation prefixes
refresh all loaded pages. Source order selectors in shipments share this navigation. No new
permission, persisted browser business cache, or client-side cost reconstruction is introduced.
Purchases now share50-record cursor navigation, filtered by the current sales order. Until all
pages load successfully, the commitment strip explicitly reports an unavailable total rather
than presenting a partial sum as complete. Loaded rows survive page failures; retry/restart
controls use the shared cursor component without introducing an alternate cache boundary.

ADR-024 purchase approve/send send displayed row counters with stable unchanged-input keys.
Supplier confirmation freezes the form's opening version; refetch never silently rebases it.
Explicit original-variable retry preserves action/version/reference/date through background changes.
Fresh decisions require reviewing refreshed facts; finalized parents hide fresh decision controls,
while authorized exact receipt recovery remains possible. Existing session-keyed parent remounts
discard local retry state. Pending/errors and protected cost fields retain existing styles/policy.

ADR-023 order creation keeps unchanged input/key across uncertain-response retries, rotates
after edits and synchronously guards duplicate submissions. Failed fields remain usable;
guidance explains committed-response loss and the one-order-per-quotation/conflicting-deposit
rule. The form is keyed by organization/session and does not persist keys in browser storage.

ADR-022 order confirmation sends the displayed row counter with a stable unchanged-body key.
An explicit retry retains original mutation variables after background refresh; a fresh decision
uses newly displayed data. Order/session/organization-keyed detail remounts discard local retry
state. Pending and permission controls remain, with clear stale-version/reload guidance. Existing
visual styles and FastAPI business authority are retained; no new design system or stored keys.

0030 adds a separate purchase source-review section and independent per-history-entry review.
Source descriptions and cancellation evidence display protected labels until server-authorized;
supplier confirmation numbers, SKU/unit, quantities and dates remain usable. No purchase prices
become visible through source release. Shared review controls retain explicit decisions, exact
version/digest, pending feedback and session scoping. Source review refreshes purchase/order
queries so open old-version receipt editors become stale instead of silently changing versions.
Historical receipts can be reviewed without order.read or procurement.write, but procurement.read
and profit.read remain mandatory. The existing ledger styling is retained.

0029 order snapshot text uses explicit protected labels for descriptions and terms. An independent
exact-version review stays separate from source quotation approval, order confirmation/completion
and contract disclosure. Review refreshes the order query; selling quantities/money remain usable.

Order snapshots and supplier commitments come from backend commands. Procurement receiving uses
React Hook Form/Zod for input feedback and the generated OpenAPI request contract. Decimal strings
are sent unchanged; backend rules determine quantity limits and state transitions.

Receipt/close controls require procurement.write; operation history requires procurement.read.
Receipt retries retain their command key for an unchanged request. A version conflict requires
refresh and review. Closure does not assert supplier payment settlement. Query caches are mounted
within the root identity/organization session boundary.
The open receipt/closure editor is bound to its starting version and explicit operation. A query
refresh invalidates an old editor even if its unmounted mutation loses the success callback;
receipt completion never implicitly opens closure. The user must review and reopen the next action.

Legacy create-order, create-purchase and supplier-confirmation forms now use RHF/Zod as well.
Field errors are announced next to inputs; pending inputs/cancel controls are disabled and failed
commands retain entered values. Decimal/rate strings are never converted to Number for payloads.
Creation/confirmation/approval controls use their corresponding member permissions and finalized
orders do not offer new procurement. The existing isolated-test connection form also uses RHF/Zod;
this does not change production Logto authentication. No response-field policy is implied.
Purchase creation now sends a durable command key. An unchanged in-form retry retains the same
key and exact payload; changed input receives a new key. A lost response may mean the original
purchase committed: check the list before editing, closing or reopening the form. Keys are scoped
to the mounted organization/session form, not stored with business data in browser storage.

Cancellation/replacement controls require procurement.approve, profit.read and explicit human confirmation.
Replacement forms create a new unapproved draft without overwriting original purchase facts.
Unchanged retries preserve the command key; disabled fieldsets prevent edits during submission.
The commitment strip sums backend retained decimal strings using fixed-four-place BigInt
arithmetic, so cancelled original totals do not overstate continuing commitments.

The order detail now includes the ADR-015 contract panel from features/contracts: frozen selling
terms, draft maintenance, role-sensitive uploads/signature recording and exact evidence downloads.
Contract events appear in the existing order timeline. Contract signing never confirms or settles
the order implicitly.

ADR-020 order snapshots now arrive with nullable protected cost/profit fields. Order-line cost
and profit columns render only with profit.read; otherwise the table explains the restriction
and retains quantities, sales prices and sales totals. Missing privileged values show unavailable,
never a fabricated zero. A missing order-cost default becomes an empty purchase-form input,
not a zero cost. Procurement cards and the commitment strip now hide purchase amounts without
profit.read, and creation/approval/replacement additionally require cost authority. Operations
can still send/confirm/receive/close without entering costs. Missing commitment amounts remain
unavailable rather than becoming a partial or zero sum. Restricted history uses readable event
labels without restoring manager-authored summaries. Full policy acceptance remains pending.
Browser checks verify actual returned fields under manager/sales/operations role switches and
the preserved selling facts. The existing narrow-screen table scroll stays inside its region.
