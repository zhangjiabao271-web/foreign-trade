# Task006 acceptance mapping

Checkpoint 2026-09-09. This mapping concerns Task006, not the complete V1 goal.

## Related company isolation reconciliation: 2026-09-09

Read complete company role/archive routers and conversion-port tests. Extended the existing
foreign archive test with company-name,role and combined filters: exact empty page response,
including has_more=false/next_cursor=null. Foreign add-role requires404/COMPANY_NOT_FOUND.
After all denied writes/reads,the original company response (including roles/version) and
activity/audit/outbox counts remain unchanged. New archive+conversion-port run17passed/19.48s,
exit0,existingwarning; tmp/company-final-20260909.xml. Ruff check/format,diff and focused
code-simplifier review passed; explicit filter cases retained without new abstraction.
The seven owner-port cases were now read in full and executed, covering permission before DB
access,separate same-name tenants,caller rollback with/without existing company,source/contact
preservation and replay,CRM invocation with post-port failure,and missing-contact fallback.
Together with the preceding lead,contact,parent,cursor,company-role,conversion and browser
evidence,this reconciles the specifically identified related-company isolation gap. Task006's
named conversion/multi-role/idempotency/search outcomes have direct local evidence. This does
not generalize to every later domain/API nor replace the remaining whole-guide acceptance.
Only a test and documentation changed; no runtime deployment or user-data/provider operation.

## Browser search/filter supplement

Extended the existing complete lead conversion Playwright journey with company-name and
contact-name searches, mixed-case input, combined NEW/CONVERTED selection, explicit empty
results and restored matching results. Checks are scoped to the manifest so the still-open
detail cannot masquerade as a matching list item; the original five timeline records remain.
New execution of lead-conversion.spec.ts:6passed/28.3s,exit0, including the expanded main
journey, keyboard skip and four viewport overflow checks. This uses fixture auth and a
dedicated local API/Web, not the user's live Logto session. No provider calls were enabled.

Preflight and postflight independently found the dedicated E2E database absent, ports3100/8010
unused and fixture/process receipts absent. Teardown removed only the synthetic test database
and test processes; no business database or retained recovery volume was removed. Source types
passed. Initial formatting check required line wrapping; mechanical Prettier formatting and
subsequent format check passed. The browser run preceded whitespace-only formatting.
Focused code-simplifier review retained direct actions and scoped assertions rather than
adding a generalized test helper. Full-suite totals from earlier checkpoints predate this
test extension and must not be presented as a new full-browser run.

## Search/filter execution supplement

Added `test_lead_search_and_status_filters_preserve_tenant_scope_and_facts` to the existing
CRM acceptance matrix after finding no direct combined search/status case in the CRM tests.
Fixture preparation uses API commands for three A leads and one matching B lead. Six A
queries check case-insensitive company/contact matching, combined NEW/QUALIFIED filtering,
status-only and no-match results with exact IDs/counts and persisted organization ownership.
B's same-name/same-status query returns only its own ID. All lead status/version snapshots
and company/contact/opportunity/activity/audit/outbox counts remain unchanged by reads.

Initial run failed on a test-only assumption that LeadResponse exposed organization_id;
the actual schema does not. The test now checks database ownership instead of changing the
contract. Initial cache permission warnings were avoided with a workspace tmp cache directory.
Final complete CRM matrix plus vertical slice:33passed,1existing Starlette/httpx warning,
35.70s,exit0. Report:`tmp/crm-search-final-20260909.xml`. Ruff check/format pass. Applied
code-simplifier review to the new test only: retained explicit fixture identities and expected
ID sets, with no behavior-changing simplification. No application code or deployment changed;
random disposable test databases are managed by the existing fixture, not the business database.
This closes the combined API search/status/tenant evidence gap, not browser filter interaction.

Read the CRM/Companies/Lead UI READMEs, CRM services/repositories, Companies conversion
port, both CRM test files below and the full lead-conversion Playwright specification.

Existing `tmp/full-owner-20260909.xml` was extracted: crm_vertical_slice4 and
crm_acceptance_matrix28, total32, no failure/error/skip. This extraction is not a
new test run. The same report contains7company_conversion_port cases, but their
bodies were not part of this pass and their count is not used to extend its claims.

| Named requirement                      | Directly inspected evidence                                                                                                                                                                                                                                                                                                                                         |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NEW through CONVERTED                  | `test_complete_lead_conversion_and_multiple_company_roles` exercises qualify/contact/respond/convert by API and checks each status. Browser specification creates the lead, follows each button and verifies persisted conversion after reload. Prior browser execution is recorded separately in V1_STATUS; the specification alone is not new execution evidence. |
| Repeated conversion idempotent         | The same test repeats conversion and compares the exact result; database counts are one company/contact/opportunity. Matrix adds two concurrent conversions of one lead, matching IDs and exact one-set increments.                                                                                                                                                 |
| Company CUSTOMER and SUPPLIER roles    | The vertical test adds SUPPLIER after conversion, repeats role creation and checks the same role ID, one company and exactly both roles.                                                                                                                                                                                                                            |
| Allowed/illegal status transitions     | Matrix defines expectations independently of the implementation and checks seven states against five commands; rejected commands retain state and evidence counts. Separate conversion-state matrix covers entry, replay and illegal states.                                                                                                                        |
| Permissions and organization isolation | Six-role matrix checks every lead command through HTTP; forbidden cases also call the service and verify no changed snapshots/counts. Foreign-ID matrix checks every lead command returns404. Vertical test checks foreign detail and empty list/count. This is not yet the complete related-company/contact/search matrix.                                         |
| Atomic evidence                        | Conversion failure is injected independently into activity/audit/outbox INSERTs; no company/role/contact/opportunity/evidence or conversion reference/time survives. Vertical create-outbox failure checks lead and all three evidence counts remain zero.                                                                                                          |
| Company reuse under concurrency        | Matrix coordinates two distinct same-name lead conversions, both with and without an existing company. They share one company/customer role but keep separate contact/opportunity records; archived customer role is rejected without resurrection.                                                                                                                 |
| Ownership and preserved source         | CRM retains lead locking, opportunity creation, conversion references/time and evidence in one UnitOfWork. Companies owns party writes through immutable ConversionSource/ConversionParties and independently checks lead.convert; it does not commit.                                                                                                              |

## Related archive and migration supplement

Read complete base migration20260903_0004 and current CRM/Companies models. The migration
creates companies/roles/contacts/leads/opportunities/activities, organization-scoped keys,
normalized active company uniqueness and composite tenant foreign keys between conversion
objects. Current models retain those tenant relationships and add later review/navigation
fields/indexes. CRM schemas and routers were also read in the search-test pass: separate
create/read/conversion models and explicit permission-gated state commands exist; no generic
status write endpoint is exposed by that router.

Read complete test_company_archive.py and the two selected opportunity lifecycle tests.
New run:9archive+2opportunity cases,11passed/7deselected,15.24s,exit0 with existing warning;
`tmp/crm-related-20260909.xml`. Archive tests cover exact company/contact updates and role
unification, foreign company detail/contact list/history/write/cursor rejection, wrong-parent
contact detail/update rejection, independent activity/audit/outbox rollback for company and
contact, concurrent duplicate company creation, legacy0014 upgrade and Alembic model check
with preserved company output. Opportunity cases cover foreign detail/history/loss/list and
cursor rejection, authorized two-page traversal, and protected loss replay/permission behavior.
Every selected test starts from its disposable database migration to head; this is not another
production migration or a claim that the destructive base downgrade is safe for business data.

Contact supplement: added test_foreign_contact_detail_update_and_cursor_preserve_original.
Normal API commands create a real A company/contact and B company. B cannot read or update
the contact under its actual A parent, nor use its cursor under either A or B parent. B's own
contact list remains empty; A reads the exact unchanged original including version, with
unchanged evidence counts and exactly one persisted contact. Newly ran full company archive:
10passed/13.77s,exit0,existingwarning; tmp/company-contact-scope-20260909.xml. Ruff check/format
passed and code-simplifier review retained the explicit setup/action/assertion structure.
Only a test was added; no production deployment needed. This closes the specific foreign
contact detail/update/cursor gap identified above without relaxing any existing assertion.

The named browser search/filter evidence is now present. Final whole-guide reconciliation
must retain the separate test/runtime scopes above. Lead query source filters organization and
deletion through TenantRepository; activity queries independently include organization and
subject. Source filters alone are not a complete executed isolation matrix. No current business
data, credentials, deployment or provider call changed during this review.
