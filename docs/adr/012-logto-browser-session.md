# ADR-012: Logto browser login with server-held tokens

Status: Accepted within the authorized V1 login implementation scope.

Use the official MIT-licensed `@logto/next` 4.2.10 SDK with Next.js App Router.
Logto performs OIDC login, callback validation, token refresh and logout. Browser
business requests use a same-origin backend proxy; access/refresh tokens stay in
SDK-encrypted HttpOnly cookies and are never returned to client components or logged.
The proxy supplies the API-resource access token and rejects cross-origin writes.

The browser stores only a selected local organization and an opaque non-authorizing
session marker. The API remains authoritative for active users, memberships and fixed
roles. A verified user may list only their own active local organizations before choosing
one; selection does not create membership or grant permissions. API tokens are for the
business resource, not Logto organization tokens with a different identifier model.

All workspace connection screens use the same login/organization selector. A missing
provider configuration is an explicit setup state, never a silent switch to test auth.
The existing bearer-token fixture path is allowed only by an explicit local test flag
and is forbidden in production. Session changes clear client query caches.

Local acceptance will use a self-hosted Logto instance with its own persisted database.
This does not choose a production hosting provider. A production deployment must supply
its own endpoint, application credentials, HTTPS base URL and cookie encryption secret.
Secrets are supplied by environment/secret storage; no chat-supplied keys are persisted.

Official sources verified 2026-09-06:

- https://docs.logto.io/sdk/next-app-router
- https://github.com/logto-io/js/tree/master/packages/next
- https://registry.npmjs.org/@logto/next/4.2.10
- https://github.com/logto-io/logto/releases/tag/v1.43.0

Acceptance requires real redirect login/logout, invalid-state callback rejection, member
selection, inactive/unmapped-user denial, cross-origin write rejection and the existing
two-organization business tests. Scripted tokens alone do not prove real login acceptance.

Algorithm agreement follow-up (2026-09-06): the local issuer discovery and JWKS advertise ES384
with an EC P-384 signing key. The adapter now accepts an explicitly configured single algorithm,
RS256 (existing default) or ES384, rather than hard-coded RSA only. It never infers policy from
an unverified token; header/key algorithm/type and EC curve must match. This is configuration
compatibility within the same OIDC adapter, not a new provider, auth bypass or membership change.
Real login and initialized provider recovery remain separate acceptance requirements.
