# ADR-028: Safe, uniform request error responses

Status: Accepted implementation decision under the authorized guide-completion work,2026-09-08.
This implements guide9.3, not a change to business permissions or financial rules.

Before V1 release, normalize FastAPI request validation failures and Starlette HTTP exceptions
to the existing ProblemDetails envelope. Existing ApiProblem codes/details remain unchanged.
Validation keeps422 and uses REQUEST_VALIDATION_ERROR; framework HTTP errors use HTTP_<status>
and standard HTTP phrases, never arbitrary exception detail. Preserve protocol headers Allow,
WWW-Authenticate and Retry-After, and always use the established request ID.

Validation entries expose only a fixed source category (body/query/path/header/cookie/request)
and a fixed category code. Do not echo input, validator context/message, URLs, dictionary
keys or arbitrary location segments; field-level interactive guidance remains in existing forms.
Limit public entries to100. This protects malformed JSON and extra-field names as well as values.
No body logging, schema migration, audit/outbox writes or change to validation/auth ordering.
Unhandled programming/response-validation errors are not converted into client422 errors.

The old framework detail-array format is intentionally not retained as a compatibility path.
Update contract evidence and verify frontend parsing, auth/tenant rejection, malformed input,
protocol headers and body confidentiality. Deployment and whole-suite acceptance are separate.
