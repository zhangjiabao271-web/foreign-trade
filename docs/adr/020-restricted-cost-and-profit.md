# ADR-020: Restricted cost and profit visibility

- Status: Accepted policy; catalog/order/procurement snapshots implemented, remaining enforcement and acceptance pending
- Date: 2026-09-06
- Authority: User explicitly selected “成本和利润均仅限管理员、经理、财务；销售和运营不查看成本”.

## Decision

Only ADMIN, MANAGER and FINANCE may read structured business costs or profits. SALES,
OPERATIONS and VIEWER must receive redacted responses, not merely hidden UI text. Existing
`profit.read` is the explicit permission covering both cost and profit snapshots; it is not
granted to SALES/OPERATIONS. Money facts remain exact and unchanged in PostgreSQL.

Protected values include product standard cost/cost currency, supplier reference prices,
quotation/order cost currency/rates/allocated costs/line and total costs/profits/margins,
procurement unit prices/totals/converted and retained commitments, expenses and supplier
settlements. Sales prices, customer receivables and receipts are not internal costs and remain
under their existing permissions. Sales-side tax/freight charged to the customer is distinct
from internal allocated costs. No missing/hidden value is represented as a zero business fact.

List/detail/command/replay responses, timelines, search/overview projections and AI tools
must obey the same restriction. Read-only redaction must not mutate ORM facts or cached
business snapshots. API contracts explicitly model unavailable values; owned clients handle
them without computing a fake margin or sending redacted nulls back as replacements.

## Workflow consequences

- Product cost-bearing creation and supplier-price maintenance are handed to existing
  authorized managers/admins. FINANCE retains its existing write permissions; visibility
  alone does not grant product, quotation or procurement authoring authority.
- Sales continues commercial drafting using product/source snapshots resolved on the backend.
  Cost overrides, cost currency/rates and internal allocations require cost authority.
  A revision without cost fields preserves the original cost snapshot, not a new zero/default.
  New or cross-currency costing that cannot be resolved from an existing valid snapshot must
  request manager preparation rather than invent an exchange rate or allow a blind override.
- Operations retains non-price fulfillment/receipt work. Cost-bearing procurement creation,
  amendment and commercial approval require an authorized manager/admin; operational readers
  see quantities, dates, status and references without purchase amounts. Commands that return
  purchase facts must use the same protected projection.
- Audit/outbox remain restricted. Activity metadata and AI historical outputs need explicit
  review for cost-bearing content, including membership changes after data was produced.
- Arbitrary user-authored text and uploaded binaries are not automatically safe merely because
  structured fields are redacted. Document confidentiality/classification and historical free
  text must be assessed before claiming complete protection; no automatic content scanner is
  assumed and no historical record is silently rewritten.

### Accepted attachment and free-text release policy

The user additionally confirmed default confidentiality with review before release. Unreviewed
attachments and free text, including historical content, are not available to SALES/OPERATIONS
or VIEWER. ADMIN/MANAGER/FINANCE may explicitly review and release content only after confirming
that it contains no internal cost/profit information. Domain read permissions still apply;
review authority does not grant unrelated business authoring permissions.
Implementation must preserve original evidence, bind release to the exact reviewed content/version,
invalidate release when content changes, and audit the reviewer and decision. This is human review,
not automatic malware detection or a claim that an existing file type guarantees confidentiality.

The user further confirmed that business identification fields such as company names, contact
names and product names remain visible under their original business permissions. Users must not
enter internal costs/profits in those fields. This is an explicit policy boundary, not a scanner
guarantee. Notes, descriptions, terms and historical prose remain confidential until reviewed;
do not disguise narrative notes as identification fields or release them with an entity name.

Policy is accepted. Document version migration 0024, review/restrict commands, protected
service projections/download signing and shared UI are implemented with final acceptance pending.
Five-minute previously issued download capabilities cannot be recalled immediately. Stored copies
cannot be remotely revoked. Free-text records outside documents remain separate unfinished work.

Order Work text slice (0025) now implements task/activity review metadata, protected query and
completion/replay DTOs, order-scoped human review commands and frontend controls. The release
digest includes the resulting record version as well as exact text/details, so any later update
requires review again. Tasks and historical activity bodies are preserved. This is not yet the
complete free-text policy. CRM/company/opportunity/customs/refund timeline queries now use the
same protected projections and explicit subject-scoped human review with original domain access;
independent entity notes and AI historical output still require separate integration. See
V1_STATUS for actual acceptance, not schema presence alone.

CRM source slice (0026) separately protects Lead notes and unconstrained source explanation,
plus Opportunity lost_reason, at query and command/replay service boundaries. Business identity
fields stay visible. Source disclosure review is domain-authorized, exact-version/content-bound,
atomic and revocable; it never advances business status or releases timeline entries. Later row
changes invalidate release even when old content is restored. Shared metadata/request/snapshot
primitives do not confer authority across domains. Historical facts remain unchanged, and a
populated downgrade is rejected to prevent re-exposure. See V1_STATUS for tested evidence.

Export source slice (0027) applies the same separate content/version review to original case
notes/rejection_reason and all service outputs, including creation replay and follow-up/state
commands. Review remains available after finalization but never reopens business state. Case
numbers and manual submission receipt references are identifying fields under the confirmed
user rule, not narrative notes: keep them visible and prohibit internal cost/profit entry.
This classification does not claim automatic sensitive-content detection.

## Conflicts and acceptance

Commercial source slice (0029) adds independent reviews for Product.description,
Inquiry.description, QuotationVersion and SalesOrder descriptions/payment/delivery terms, and
SalesContract notes plus its nested commercial snapshot text. RFQ customer references and
external contract numbers are identifying fields, like the previously classified receipt IDs:
retain original read access, forbid cost/profit entry. Description/terms cannot be moved into
those identifiers as a workaround. JSON review binds the exact contract snapshot; quote/order
review also binds line IDs/versions, preventing restoration from restoring an old approval.
New copies/revisions never inherit disclosure. Raw ORM copying preserves source facts while
service DTOs protect all direct reads and commands/replays. Price-only frontend revision omits
description overrides. Omitted contract update fields preserve originals (explicit null clears
an authorized draft field); the owned editor disables and omits confidential original notes.
Parent-first review locks match commercial command ownership, and do not reopen signed/final
records or perform their business approvals. See V1_STATUS for ongoing acceptance results.

Customer receipt source slice (0028) protects Payment.notes in every payment query and command
projection, including durable allocation/creation replay and status-based reversal replay.
Bank receipt references/payment numbers are identifiers under the confirmed user rule and stay
visible with the original payment permission; entering cost/profit there is prohibited. Exact
notes/version review requires both original read and cost authority and records atomic evidence.
Each appended reversal has its own confidential notes and review; approving the original receipt
does not approve a reversal. Review never modifies financial amounts, allocations or status.
This is source disclosure review, not approval of bank movement or release of timeline entries.

This overrides the former SALES/OPERATIONS supplier-price access and cost-bearing controls
described in module READMEs. It refines guide role workflows under the user's explicit choice,
not an inferred grant or removal of unrelated permissions.

Acceptance requires all six roles, foreign organizations, serialized sensitive-field absence
or null, rejected unauthorized cost inputs with no writes/evidence, safe sales drafting and
revision cost preservation, operations quantity workflows, AI/current-membership checks,
generated-client drift, browser role journeys and unchanged exact privileged calculations.
The currently passing 401 backend / 161 frontend / 25 browser tests predate this policy's
implementation and must not be represented as its acceptance.

## Implementation checkpoint

Procurement source slice (0030) independently protects line descriptions, cancellation_reason
and cancellation_reference (the legacy cancellation evidence field accepts narrative evidence).
Supplier confirmation numbers and booking references identify supplier/transport commitments:
retain their original read rights, prohibit cost/profit entry. Receipt reference historically
accepts a number or explanation; preserve it in its independently reviewed activity rather than
assuming all historical values are safe identifiers. Purchase source release binds row/line
versions and exact prose; receipt/amendment changes invalidate release, and replacements never
inherit it. Review locks sales order then purchase and does not change commitment facts.
Purchase activity review uses existing0025 exact-content metadata and procurement.read, not
order.read or procurement.write; source and individual history approvals remain independent.
Structured purchase costs remain restricted even after source text release. See V1_STATUS.

Catalog product queries now return detached projections with null cost/currency when profit.read
is absent. Supplier-reference list/detail/history/names and write/replay boundaries require
profit.read in addition to domain permissions. Product creation is manager/admin only; FINANCE
read access does not grant authoring. Basic product browsing remains available to other roles.
Sales-order query/create/confirm/completion services now return protected detached projections,
including command replay. Sales selling facts and stored complete commercial snapshots remain
unchanged. See catalog/order checkpoints in V1_STATUS for exact evidence and test boundaries.
Procurement query/command/replay boundaries now project protected snapshots, and priced commands
require cost authority. Operational quantity/date workflows remain available; restricted history
omits free-text summaries and non-allowlisted result fields. See V1_STATUS for verification.
Quotation projections and protected-input checks are now implemented, with final regression
acceptance still running. Sales source-bound revision inherits costs without sending them back;
unresolved cross-currency costing requires manager preparation. See the quotation checkpoint.
This does not yet close AI historical confidentiality, wider timeline/task details or arbitrary
documents/free text.
