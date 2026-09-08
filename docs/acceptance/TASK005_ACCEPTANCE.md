# Task005 client generation acceptance checkpoint

Checkpoint 2026-09-09. This is a partial mapping, not a Task005 or V1 completion claim.

## Whole-runtime type declaration reconciliation: 2026-09-09

Subsequent TypeScript compiler-API traversal parsed all106 non-test .ts/.tsx files under
apps/web/{app,components,features,lib},with zero parse diagnostics. Inspected the complete
printed syntax of276 type literals and101 type aliases (no interface,class or mapped-type
declarations). This includes inline function props and local state, not only top-level grep
matches. A second traversal included Zod variable initializers and nonliteral aliases.
Classifications: generated schema/path aliases and their Pick/Extract/NonNullable/ReturnType
compositions; component callbacks/route parameters; editor/disclosure/command envelopes;
retry fingerprints and keys; generic cursor/query controls; form-only Zod inputs; the already
reviewed Next-owned AuthSession/PlatformHealth wrappers. No handwritten business response
mirror was found. Business data remains generated-client inference at the previously fully
read API boundaries and component-local query hooks. This closes the outstanding declaration
inventory gap, including large workspace components, without claiming every JSX behavior or
every runtime JSON value has been validated. Form input validation is permitted by guide17.2
and is not a second authority for backend business rules.

Combined with the source-mutation negative probe, clean generation,183 unique operation IDs,
generated Lead query and shared error parser checks recorded below, Task005's named local
contract/type gates now have evidence. Remote GitHub execution is still unverified; this is
not a remote CI green claim or a V1 release certificate. The earlier open type-inventory and
literal-mutation notes below are historical. No production code was changed in this review.

## Literal response-source drift probe: 2026-09-09

Added a third negative test to drift.test.mjs. It copies the app source to a new temporary
directory, inserts drift_probe into the copied Pydantic LeadResponse, then exports through
the existing Python exporter with isolated PYTHONPATH. The test first asserts that the new
field appears as a string in LeadResponse OpenAPI; this prevents an ignored source override
from masquerading as a valid test. The unchanged Node generation check then must exit1 with
the exact canonical openapi.json drift error. Original source and both canonical generated
artifacts are byte-compared before/after; the temporary source/export are removed.
All three negative cases passed,21.533s,total exit0. Subsequent normal generation check passed,
as did Prettier and diff check. Focused code-simplifier review retained explicit source mutation,
export verification and exact failure assertions. No production code/dependency/runtime change.
This supersedes the earlier literal-Pydantic-probe question below. Whole-Web type review and
remote CI execution remain separate; Task005 and V1 are not declared complete.

## Completed API-boundary body review

Additional Sep9 component/transport pass: read complete resume-upload, identity-form,
finance/supplier-form, inquiry-source, platform/use-jobs, system-health and backend catch-all
route bodies. ResumeUpload aliases generated DocumentResponse/DocumentVersionResponse;
IdentityEdit/SupplierEdit wrap generated entities with editor modes. Their Zod input schemas
describe form-only strings, confirmation and selection fields; typed command unions constrain
the resulting API bodies. InquirySource and useJobs return inferred generated-client data.
SystemHealth uses the Next-owned parsed health aggregate. The backend proxy streams the
upstream Response body and does not define a mirrored business DTO; RouteContext is Next route
parameter state. Whole-Web typecheck newly passed,exit0. No application changes or UI tests
were performed in this read-only pass. Earlier combined output truncated supplier-form and
failed the bracketed route path; both were subsequently read completely using the literal path.
The inventory has106 non-test TS/TSX files across app/components/features/lib. Searches alone
are not full inline-type/body coverage; remaining large workspace/form components still need
reconciliation. useJobs and SystemHealth currently have no source callers (reference search
finds declarations only). The legacy useJobs cache key is not session-scoped; do not introduce
it into a live session-switching page unchanged. This observation is not a current-page leak
or a duplicate-DTO finding, and no runtime behavior was altered.

The subsequent review read all 18 feature API modules completely, not only declaration
search results: leads, companies, catalog, contracts, orders, quotations, shipments,
finance/api, finance/expense-api, finance/supplier-api, identity, opportunities, export,
overview, platform/api, platform/operations-api, ai/api and ai/disclosure-api.
Business response types are generated aliases or inferred generated-client results;
request bodies use generated types and typed client calls. Command envelopes add UI
actions, IDs and retry keys rather than redefining a server DTO. Export ManualFact derives
its fields with intersections/Pick/Extract/NonNullable from generated schemas.
No handwritten mirrored business DTO was found in these 18 module bodies.

Also read documents/transfer, overview/session, lib/cursor-pages and both sides of the
Next platform-health endpoint. Cursor collection accepts generic items with IDs, not a
second business response definition. Upload request metadata flows into typed client
calls; the only raw file PUT is to the authorized upload URL. PlatformHealth is a
Next-owned aggregate of HTTP readiness, not a mirror of the FastAPI readiness body.
AuthGate and the Next session route were read in the preceding review: their wrapper
retains a generated organization response. Untyped JSON decoding is a distinct runtime
validation concern; it is not evidence of a duplicated FastAPI DTO.

The next review completed the full bodies of documents/review, finance/work-review,
finance/commercial-timeline and finance/funding-estimate, plus the export document download
hook. Review snapshots alias generated schemas; review subject types derive from generated
path parameters; review request bodies are typed by the generated client. Timeline/funding
results remain inferred from generated calls. Export download uses the generated response
and does not declare a second download DTO. Form confirmation/decision fields and routing
target envelopes are UI-specific, not mirrored response definitions.

New targeted execution: document review, work review, commercial timeline and funding estimate
test files,45passed/4files,3.60s,exit0 (2026-09-09 03:48 local). These are mocked-interface
component tests, not real login/provider/authorization acceptance. No code change was made.
This closes the five specifically named component-hook candidates from the preceding pass;
it does not claim that every inline type in all other page/component bodies was inspected.

| Requirement                                | Current evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Single-direction FastAPI schema generation | Read `export_openapi.py` and `generate-client.mjs`: sorted FastAPI OpenAPI JSON feeds openapi-typescript, then openapi-fetch consumes generated paths. No database or provider call is part of this check.                                                                                                                                                                                                                                                                                                 |
| Clean artifact comparison                  | Newly ran `node packages/api-client/scripts/generate-client.mjs --check`, exit0. Both temporary generated artifacts match canonical bytes.                                                                                                                                                                                                                                                                                                                                                                 |
| Stable operation names                     | Current snapshot contains 183 operation IDs and zero duplicate IDs; clean regeneration agrees. This proves current uniqueness/reproducibility, not stability across future route renames.                                                                                                                                                                                                                                                                                                                  |
| CI drift rejection                         | CI invokes clean check and test:drift. Newly ran drift.test.mjs:2passed,0failed,9.997s. The test-only preload simulates stale schema and stale types independently, requires exit1 and the exact matching artifact error, and verifies disk artifacts unchanged. This demonstrates byte-mismatch rejection, not an actual remote GitHub CI run or a literal Pydantic source mutation.                                                                                                                      |
| Next.js query example                      | Read `features/leads/api.ts`: useQuery/useMutation call the generated client with generated LeadResponse/LeadDetailResponse/LeadCreate/LeadStatus aliases and shared error parsing.                                                                                                                                                                                                                                                                                                                        |
| Unified errors                             | `ProblemDetails` aliases the generated schema. Read parser and tests; newly ran `lib/api-client.test.ts`:3passed,1.16s, preserving validation categories, generated errors and fallback request correlation. Initial sandbox attempt failed before tests due to Vite cache EPERM; scoped escalation ran the unchanged tests successfully.                                                                                                                                                                  |
| No handwritten mirrored business DTOs      | Review remains open for the whole Web scope. Search located generated aliases across all feature API modules, but search alone is not a complete body review. Inspected SupplierEdit/IdentityEdit are UI mode/state compositions over generated business types; UploadRetry is local retry state; AuthSession wraps the Next-owned login endpoint and embeds generated MyOrganizationsResponse, not a handwritten FastAPI business response. These findings are not reasons to remove legitimate UI types. |

No source, generated artifact, deployment, authentication configuration or business data was
changed. `apps/web/README.md` does not exist; package README and affected source bodies were
used for this read-only review. Remaining Task005 work: finish the whole-Web DTO/body review
and decide whether a literal changed-Pydantic negative probe adds necessary evidence beyond
the inspected single-direction generator and successful artifact mismatch tests. Do not
claim remote CI passed from local execution. Real AI disclosure consent remains separate.
