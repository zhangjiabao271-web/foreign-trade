# Task003 foundation acceptance mapping

## Consolidated report revalidation (2026-09-09)

Independently parsed the completed `tmp/full-reconciled-20260909.xml` rather than rerunning
tests: auth_unit6, oidc_algorithms32, tenant_isolation25 and worker tasks9, total72,
with zero failures/errors/skips in these groups. This confirms the mapped foundation cases
were included in the latest1476-pass backend/worker run. The shared worker9 cases also appear
in Task004's mapping and must not be double-counted as distinct tests. Module README reread
confirms the runtime OIDC/test-issuer distinction and explicit tenant context requirements.
This does not expand the mapping into all later domain isolation or real-provider approval.

Checkpoint2026-09-09. Scope is the named Task003 foundation, not all later domain isolation
or a V1 release certificate. Source bodies below were read and matched to terminal full-run
tmp/full-owner-20260909.xml: auth_unit6,oidc_algorithms32,tenant_isolation25,worker tasks9;
72cases total, no failure/error/skip. No new test execution is implied by report extraction.

| Task003 obligation                              | Inspected implementation and direct evidence                                                                                                                                                                                                                                                                       |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Replaceable OIDC/JWT verifier and Logto adapter | auth/tokens.py TokenVerifier Protocol and LogtoTokenVerifier; dependencies selects trusted configured adapter, test override via app state. OIDC tests use real RS256/ES384 signatures and parsed JWKs, reject mismatched algorithm/key/curve/claims. JWKS HTTP is stubbed in these tests, not a live login claim. |
| Local test issuer                               | LocalTestTokenIssuer/Verifier; unit round trip plus wrong issuer/audience/expiry rejection. Runtime default factory does not select the HMAC test adapter.                                                                                                                                                         |
| RequestContext and permissions                  | Frozen auth/context.py plus dependencies.py constructs org/user/request ID and permission set only after identity checks. Unit independent permission guard and API viewer rejection both pass.                                                                                                                    |
| Membership and organization selection           | IdentityRepository joins subject, selected organization and membership, excluding deleted records; dependencies checks active statuses and optional token-org match. Identity discovery deliberately needs token but no selected-org header and returns only permitted memberships.                                |
| No organization must fail                       | test_missing_organization_is_rejected asserts400/ORGANIZATION_REQUIRED. Missing bearer independently asserts401/AUTHENTICATION_REQUIRED.                                                                                                                                                                           |
| No member / disabled user must fail             | test_local_identity_and_membership_fail_closed separately asserts403/MEMBERSHIP_REQUIRED,USER_DISABLED,MEMBERSHIP_INACTIVE,ORGANIZATION_DISABLED.                                                                                                                                                                  |
| Wrong audience must fail                        | Local unit/API parameter cases assert TokenVerificationError or401/INVALID_TOKEN; both asymmetric algorithm cases reject bad audience as well.                                                                                                                                                                     |
| Organization B ID under A returns404            | test_cross_tenant_primary_key_returns_not_found queries B job under A and asserts404/JOB_NOT_FOUND. List/count test requires exactly A job and count1.                                                                                                                                                             |
| Tenant-aware repository base/convention         | core/repositories.py requires organization_id for get/list/count; shared selection includes organization and deleted_at. Platform repositories inherit it; auth README documents same rule for other domains.                                                                                                      |
| Background job explicit organization            | TenantTaskContext requires org/request IDs, validator parses UUIDs; worker task probes accept valid context/reject malformed one. Dispatcher tests verify org/correlation propagation. Consumer mismatch test rejects before database access.                                                                      |

The named foundation artifacts and listed Task003 acceptance cases have source and passing
execution evidence. Later requirements still need their own domain/API/tool/worker matrices;
the platform job example does not prove every later resource isolated. Real Logto setup and
sales/manager reads are separately recorded in REAL_IDENTITY/V1_STATUS and are not replaced
by the local issuer tests. No fixture roles, login settings, business facts or provider calls
were changed in this mapping review.
