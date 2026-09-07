# Product supplier references

Product original description now shows an explicit confidential label until server-authorized.
The privileged product detail includes a separate source-review form; it never releases
supplier prices or downstream quotations. Original names/SKUs/units remain usable identifiers.

Product search opens a directory of supplier reference terms: factory SKU, exact decimal unit
price/currency, lead time, quote date/validity and source reference. Company names are batch-read
by the backend; no per-row browser company request. Supplier selection reuses tenant-filtered
company search with cursor navigation. Product search uses 50-row cursor pages with named
previous/next controls, disabled loading/error forward navigation and a page-one reset after
submitted search. Query keys include organization, search and cursor; counts are page-local.

RHF/Zod forms retain exact money strings, stable unchanged retry keys and the opening version.
Updates cannot move product/supplier identity and require a reason. Sensitive supplier reads and
writes use explicit permissions; denied pages never mount data queries. Reference changes do not
reprice historical quotations or create procurement commitments. Existing ledger tokens are reused.

Form tests cover precision, reason/date/lead-time validation, unchanged retries, pending controls
and read/write permission states. Browser acceptance creates and updates references and verifies
product cost remains unchanged; 375/1440 screenshots are reviewed. Exact run results and broader
acceptance gaps are recorded in docs/acceptance/V1_STATUS.md.

ADR-020 separates basic product browsing from protected supplier pricing. product.read permits
the directory and basic detail view; supplier terms/history mount only with product_supplier.read
and profit.read. Cost-bearing controls require the matching write permission plus profit.read.
SALES/OPERATIONS/VIEWER receive null product cost fields from the application service, never zero
costs; the basic page explains manager/admin handoff. Credential/session changes remount scoped
views, including an in-place manager-to-sales/operations switch. Existing typography/tokens and
keyboard links are retained. Other quotation/order/procurement cost surfaces remain separate work.
