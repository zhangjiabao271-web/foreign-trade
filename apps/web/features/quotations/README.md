# Quotation workspace

The detail now mounts Work's protected, cursor-paginated CommercialTimeline in addition to the
version ledger. Opening another version/session resets history and each business revision
refreshes it. No historical activity backfill or automatic disclosure is performed.

0032 quotation queues load50 records per explicit cursor page, retain loaded rows on errors and
reset pages when status changes. Shared controls offer retry/restart and display loaded counts,
not global totals. The optional inquiry picker requires inquiry.read, loads only OPEN inquiries,
shows identifiers/date/ID without confidential prose, and fills the existing inquiry ID field.
Manual ID entry remains available. Creation invalidates inquiry pages; session-scoped caches,
protected response fields and existing command permissions are preserved.

0029 original-text policy: source inquiry preview uses the original inquiry.read permission and
separate review; current and historical quotation versions expose their own exact-content review.
Null descriptions/terms show protected labels. Product preparation accepts optional confidential
description. Price-only revision omits description for all roles so backend copying preserves
the original, including hidden text. Disclosure never follows product approval into a quotation.
Shared review controls retain explicit decision/confirmation/retry and session scoping; no new
visual system or alternate business API was introduced.

Commercial rules and API ownership are documented in apps/api/app/sales/README.md.
ADR-021 state commands send the displayed version ID/counter and an unchanged-payload retry key.
After an uncertain response, the explicit retry action uses the saved mutation variables, not
new query data from background refresh. A fresh click against newly displayed content gets new
preconditions/key; organization/session/quotation remounts clear the prior command. Retry remains
permission gated and cannot grant authority after a role change. The server is authoritative;
missing guards fail rather than silently choosing a current version. No new visual design system.
The customer-review form is permission-gated with quotation.send, uses RHF/Zod reason
validation, captures the displayed immutable version ID and reuses unchanged retry keys.
It records a human-observed fact only; it neither sends messages nor accepts the quotation.
After success the server snapshot is refreshed; CUSTOMER_REVIEW keeps existing accept/reject
actions. ADR-020 protected quotation responses now use nullable cost/profit fields.

Revision now uses RHF/Zod with exact price/rate strings, valid calendar dates, inline errors,
invalid-field focus and pending controls. Failed requests retain input and do not close the editor;
the opening version snapshot remains fixed across background refetches. Detail commands/revision
require the matching member permission. Revision always submits expected_version_id and a ref-held
retry key: unchanged input reuses it, changed input rotates it, and a synchronous in-flight guard
prevents duplicate submissions. Successful mutation refreshes server state; failure retains input.
Closing/reopening discards retry identity, so inspect the version ledger first. Query caches and
editors are scoped to the organization/session and are not reused after a scope change.

All workspace forms now use RHF/Zod. Quotation creation uses stable field-array IDs, exact
decimal strings, 1–100 lines and blank-cost/default-currency null mapping. Product/inquiry
preparation preserves backend bounds and shows field errors. Creation, preparation and detail
controls require matching member permissions; unknown permissions expose no writes. Failed
mutations retain fields; pending fields/cancel controls are disabled. Test connection validates
before storing credentials and is not real Logto acceptance. Inquiry uncertain-result recovery
remains separate from form validation. Revision retry is explicit, not automatic.

Inquiry preparation now preserves the first received_at and Idempotency-Key alongside an
unchanged-input fingerprint. A synchronous guard prevents duplicate submissions before pending
state renders. Uncertain responses retain fields and explain manual unchanged retry; edits rotate
the key/timestamp. Successful recovery returns the original inquiry. No key or confidential input
is persisted to browser storage, and scope/close/reload remounts discard the local retry identity.
The backend owns current permissions, transaction facts and replay; no automatic retry is added.

Quotation creation now sends a ref-held Idempotency-Key: identical validated payloads reuse it,
edited payloads rotate it and a synchronous in-flight guard prevents double submission before
React renders pending state. An uncertain response retains fields and explains unchanged retry.
The backend returns the original quotation with current protected snapshots, not a second quote.
Scope remount and closing/reloading discard retry identity; the UI tells users to inspect the
quotation queue first afterwards. Keys and confidential form contents are not saved in storage.
The shared FastAPI command architecture remains authoritative over generic Server Actions advice.

Revision submits the exact source_item_id for every displayed line, including repeated products.
The backend validates that source within the current organization/version and preserves SKU/unit
and commercial defaults from that snapshot. The browser does not supply authoritative SKU/unit.

ADR-020 product preparation now requires product.write plus profit.read. Sales retains inquiry
preparation while product costing is handed to managers/admins. This gate does not yet implement
the separate quotation cost-response/draft/revision policy; do not conflate those acceptance scopes.

Quotation cost columns and profit visualization now require profit.read; absent privileged
values show unavailable, not zero. Creation omits protected inputs for sales and explains manager
preparation when cross-currency costs are unresolved. Manager costing requires an explicit rate,
not a prefilled cross-currency one. The price-only revision editor sends source IDs and selling
inputs for all roles, leaving cost/rate/allocation inheritance to the backend instead of writing
redacted nulls back. Final acceptance is in progress; arbitrary prose/binaries remain separate.
