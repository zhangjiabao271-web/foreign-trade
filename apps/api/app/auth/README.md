# Authentication and tenant context

Protected requests use a bearer JWT plus `X-Organization-ID`. The runtime verifier is the
`LogtoTokenVerifier` OIDC adapter; tests inject the local HMAC issuer/verifier without changing
runtime configuration. A valid token is not sufficient: the selected organization, local user,
and membership must all be active.

OIDC_SIGNING_ALGORITHM explicitly pins RS256 (compatibility default) or ES384 for the trusted
issuer. Verify the deployment's published signing key before changing it. The token header may
only match this setting; it cannot select an algorithm or a JWKS URL. Key algorithm/type must
match, and ES384 requires P-384. HMAC/unsigned tokens are never accepted by the runtime adapter.
The local Logto 1.43.0 discovery and public JWKS were inspected on 2026-09-06: ES384, EC, P-384.
Set OIDC_SIGNING_ALGORITHM=ES384 when configuring that local provider. This does not initialize
Logto accounts, authorize membership or prove redirect login/logout and backup recovery.

`GET /api/v1/me/organizations` is the identity-discovery exception to selected-organization
headers: it requires a verified token and returns only that subject's active, non-deleted
memberships in active organizations. A token organization claim further restricts discovery.
It never provisions users or memberships. Business endpoints still require the selected
organization and independently recheck authorization on every request (ADR-012).

Routers check explicit permissions through `require_permissions`. Application services repeat
the permission check, and repositories require `organization_id` for every get/list/count call.
Cross-organization identifiers are therefore returned as `404`, not `403`.

Business Celery tasks must accept a serialized `TenantTaskContext` containing at least
`organization_id` and `request_id`. Celery headers and result state are not business facts.

ADR-028 normalizes request validation and framework HTTP errors to ProblemDetails. Validation
uses422/REQUEST_VALIDATION_ERROR and at most100 fixed source/category entries; no submitted
values, arbitrary field keys, custom validator messages or context are reflected or logged.
Framework HTTP errors preserve status and Allow/WWW-Authenticate/Retry-After, with standard
phrases instead of exception details. Existing ApiProblem and authentication ordering are
unchanged. Internal programming/response validation exceptions are not disguised as client errors.
