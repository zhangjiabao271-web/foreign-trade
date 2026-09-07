# Finance UI

The shared review form additionally supports purchase source text and purchase_order activity
history, each using procurement.read plus profit.read. Source route permissions use an explicit
map rather than a growing conditional; neither review grants purchasing or financial authoring.

Customer receipt cards now show protected note labels or the server-authorized original notes,
with an independent exact-version reviewer using payment.read plus profit.read. Receipt recording
accepts optional default-confidential notes, separate from the identifying bank reference.
Review refreshes both receipt and order-finance queries; shared no-default decision, confirmation,
retry key, pending controls and session-scoped remount behavior are retained. It does not allocate,
reverse or change a receipt. Existing ledger styling is reused without changing business actions.

Order details host receivable generation, payment recording, allocation, reversal,
task resolution, completion and a timeline. Forms use React Hook Form and Zod;
types come from the generated OpenAPI schema, and backend commands own every rule.

Order-finance command forms require the corresponding current member permission separately:
receivable.write, payment.record/allocate/reverse, task.write and order.complete. Unknown or
loading membership grants no commands. Read-only users retain receipt search and protected
history; open tasks keep their actual labels rather than appearing cancelled. Completed-order
archive text remains visible without granting completion permission. Backend checks remain
authoritative; these gates do not change financial/state rules or grant content disclosure.

Command keys are retained during a failed form submission and regenerated after success.
Amounts remain decimal strings. Current organization is included in financial query keys.
The receipt query is scoped on the server to the current customer and order currency.
Pages contain 20 rows ordered by receipt date, creation time and ID; previous/next navigation
reaches older receipts without loading the whole organization. Search matches receipt numbers
and bank references literally and case-insensitively. A search resets the cursor and allocation
selection; failed receipt queries can be retried without discarding the receipt recording form.
Payment writes invalidate receipt pages as well as order finance. Backend settlement rules and
exact decimal strings remain authoritative; a displayed page is not a customer balance total.

Timeline entries wrap unbroken event names and historical references inside their container.
Narrow-screen regression includes long supplier-payment event keys, not only loaded headings;
the business event text remains intact and the page does not hide horizontal overflow.

Order Work text uses server-projected visibility: protected titles/body receive explicit labels,
not empty-looking records. Authorized readers can inspect the full JSON supplement; reviewers
open an exact-version text/details snapshot before making a no-default release/restrict decision.
RHF/Zod, in-form retry keys, disabled pending controls and session-scoped queries are retained.
Completed tasks remain reviewable; task completion still follows backend permissions/state rules.
Text review is separate from business approval and cannot approve a task or complete an order.
The same form supports lead/company/opportunity/customs/refund activity targets using generated
subject-route types and original domain read permissions, without requiring order.read. Queries
and remount keys include the full subject and session. Minimal timeline views retain their original
summary-only shape; the privileged reviewer still inspects every JSON field before release.

OrderExpenses adds permission-gated incurred expense recording and immutable full reversals.
Cost classification has no default: the operator must reconcile whether quotation costs already
include the charge. RHF/Zod validates decimal strings, evidence and explicit confirmation; the
backend owns FX/date/precision and financial rules. Original opening versions and unchanged retry
keys are preserved. Queries are organization/order scoped and paginate 20 facts. Server summary
is an adjusted forecast, never actual profit; expense records never claim a supplier was paid.
The UI preserves the existing ledger tokens, inline validation and responsive fact cards.

PurchaseFinance mounts on demand in each purchase card and requires both supplier financial read
permissions plus profit.read before fetching. A missing purchase currency prevents settlement
form mounting/submission instead of becoming a fabricated currency. Payables are scoped to that purchase; payment pages intentionally
show the same supplier/currency's receipts of outgoing-payment evidence across purchases.
The UI never labels those payment totals as the current purchase's paid balance. Each list uses
independent previous/next navigation; selecting an allocation preserves the opening payable and
payment snapshots. RHF/Zod forms require reason and confirmation, retain unchanged retry keys and
disable editing while pending. Creation, zero-net void, payment recording, allocation and full
reversal are separate generated-client commands. Labels explicitly disclaim transfers/refunds.
