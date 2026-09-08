# Remaining text protection inventory

Source inspection: 2026-09-06. This inventory is not acceptance and does not narrow V1 scope.
ADR-020 is authoritative. Company/contact/product identification stays visible under original
permissions by explicit user decision; entering costs in those identifiers is prohibited.

## Sep9 current commercial-history supplement

The old statement below that shipment history has no exposed route is superseded. Current
fulfillment/routers.py exposes /shipments/{id}/activities through WorkQueryService; quotation
activities and sales-order activity-history use the same protected projection. Read complete
Work services,content,timeline and activity_access bodies plus fulfillment response schemas
and the relevant router body. Owner/domain-read permission is checked before the tenant-bound
timeline query; cursor anchors additionally bind subject type and ID. Unreleased summary/details
are null/empty for low roles,while source rows remain unchanged; release hashes include owner,
organization,record/version,text and details. This is distinct from releasing shipment files.

New test_commercial_timelines.py run:3passed/7.38s,exit0,existinghttpxwarning; report
tmp/commercial-timeline-final-20260909.xml. Each of quotation/shipment/order covers105 seeded
same-time history records plus real original events,complete unique pagination,six-role cost
visibility,foreign/deleted owner denial,invalid cursor,permission refusal before any SQL,
exact-version safe-text release and confidentiality after text mutation. Query counts remain
2 for first page and3 with cursor. These are fixture identities and seeded history,not a new
live Logto browser run. No application source,runtime or business data changed in this review.
The chronology below is not a current defect list; use named newer evidence for each surface.

## Confirmed remaining source surfaces

- AI update2026-09-07: ADR-026/0033 now protects run/create/replay, tools and approval responses;
  explicit creator submission permits only candidate artifact review, appended sanitization and
  exact-version release. Original input/facts/references/tool prose and approval copies/reasons
  stay protected for lower roles, without inherited release. No global private-run reviewer access.
  See AI_DISCLOSURE/V1_STATUS for verification; the older AI source inspection below is superseded.

- CRM source group is implemented with 0026: Lead.notes/source and Opportunity.lost_reason
  use protected query/command/replay DTOs and separate exact-version human review. Final full
  regression is in progress; see V1_STATUS. Identifiers/status/conversion references stay usable.
- Catalog/inquiry and commercial snapshots: 0029 now protects Product/Inquiry.description,
  quotation/order line descriptions and terms, and contract notes/nested commercial text.
  Independent reviews bind exact records and line versions; copies never inherit release.
  Protected service DTOs include create/replay paths; source ORM copying remains exact, and
  price-only UI revisions omit description overrides. Contract omitted notes now preserve facts.
  Product/name/SKU/unit, RFQ customer reference and external contract number are identifiers,
  remain visible under original rights, and must not contain costs/profits. Wider automated
  sensitive-content detection is not claimed. Browser28, frontend192, isolated0029 runtime and
  backend662 plus corrected affected-file10 tests passed; see V1_STATUS for split-run evidence.
- Procurement0030 now protects item descriptions and cancellation prose/evidence with an
  independent source review, and supports independent purchase activity review. Source release
  never opens structured purchase prices; history command-result amounts stay filtered even after
  prose release. Supplier confirmation numbers are identifiers; legacy receipt references accept
  number or explanation and remain protected with historical activity.27 focused tests,194 Web
  unit tests and expanded28 browser tests passed, including independent receipt-history review;
  full backend finished680 passed / 6 old-fixture failures, covered by corrected27 targeted tests
  (see V1_STATUS for split-run evidence; no single all-green full-run claim).
- Fulfillment source inspection: Shipment/ShipmentItem models, response schemas, all query/create/
  replay/transition service paths and router projection contain booking_reference as the only
  user-authored text field; it identifies a transport booking, not narrative notes. It remains
  under original permissions with cost/profit entry prohibited. No item descriptions or purchase
  prices are copied into those responses. Shipment history activities are not exposed by the
  inspected shipment routes; future history reads must apply independent Work review. This is
  a source-scope finding, not full fulfillment state/concurrency acceptance.
- Export: 0027 now protects notes/rejection_reason in list/detail/create/replay/follow-up/state
  service outputs, with independent exact-version review. Full backend regression passed 597;
  see V1_STATUS. Case/receipt numbers are identifying fields under the user's rule: remain
  visible, prohibit cost/profit entry. Timeline approval never releases original source text.
- Customer finance: 0028 now protects payment notes at query/command/replay boundaries and adds
  independent exact-version review. Full backend 613, frontend 187, browser 28 and isolated0028
  build/start checks passed; see V1_STATUS. Bank references/payment numbers are identifiers:
  remain visible, prohibit costs.
  Customer selling/receivable amounts are not internal costs. Expense and supplier settlement
  routes already require profit.read; retain their existing authoring boundaries.
- AI: AiQueryService.page/get_run and AiCommandService.create/replay return original runs.
  Saved required_permissions already gates PROFIT runs after downgrade, while non-PROFIT
  arbitrary output/input and estimated provider cost need separate policy integration.
  ApprovalService.page/get/request/decide returns original proposed_action and decision reason;
  task execution approval is not a text-disclosure approval. Preserve creator-private runs,
  live membership authorization and the existing no-core-business-action restriction.

## Required pattern for each remaining slice

1. Protect at the domain service boundary, including command and durable replay responses.
2. Preserve original facts; model confidential values explicitly, not as zero or empty facts.
3. Store reviewer, decision and exact content/version binding; later content changes invalidate
   release. A privileged reviewer must inspect the entire proposed disclosure, including JSON.
4. Require original domain read permission as well as profit.read, and validate organization/
   owner relationships. Visibility authority must not silently grant business authoring rights.
5. Keep review atomic with audit/activity/outbox, concurrent decisions safe and replay current.
6. Cover role/tenant/replay/stale-content/rollback, generated contract, usable protected UI,
   browser role journey, migration and proportionate runtime checks before calling it accepted.

This file records inspection targets, not an assertion that every reference is prose or that
every unexamined endpoint currently leaks costs. Field-specific source and permission checks
remain necessary; business identifiers must follow the explicit user boundary above.
