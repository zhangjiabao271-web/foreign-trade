from datetime import timedelta
from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.auth.tokens import LocalTestTokenIssuer, LocalTestTokenVerifier, TokenVerificationError
from app.identity.enums import MembershipRole

SECRET = "unit-test-secret-with-at-least-32-characters"
ISSUER = "https://issuer.test.local"
AUDIENCE = "trade-workbench-test"


def test_local_issuer_and_verifier_validate_required_claims() -> None:
    organization_id = uuid4()
    issuer = LocalTestTokenIssuer(secret=SECRET, issuer=ISSUER, audience=AUDIENCE)
    verifier = LocalTestTokenVerifier(secret=SECRET, issuer=ISSUER, audience=AUDIENCE)

    verified = verifier.verify(issuer.issue(subject="user-1", organization_id=organization_id))

    assert verified.subject == "user-1"
    assert verified.organization_id == organization_id


@pytest.mark.parametrize(
    ("issuer_override", "audience_override", "expires_in"),
    [
        ("https://wrong-issuer.test", None, timedelta(minutes=5)),
        (None, "wrong-audience", timedelta(minutes=5)),
        (None, None, timedelta(seconds=-1)),
    ],
)
def test_local_verifier_rejects_invalid_standard_claims(
    issuer_override: str | None,
    audience_override: str | None,
    expires_in: timedelta,
) -> None:
    issuer = LocalTestTokenIssuer(secret=SECRET, issuer=ISSUER, audience=AUDIENCE)
    verifier = LocalTestTokenVerifier(secret=SECRET, issuer=ISSUER, audience=AUDIENCE)

    with pytest.raises(TokenVerificationError):
        verifier.verify(
            issuer.issue(
                subject="user-1",
                issuer=issuer_override,
                audience=audience_override,
                expires_in=expires_in,
            )
        )


def test_six_roles_map_to_explicit_permissions() -> None:
    assert set(permissions_for_role(MembershipRole.ADMIN)) == set(Permission)
    assert Permission.QUOTATION_APPROVE in permissions_for_role(MembershipRole.MANAGER)
    assert Permission.LEAD_CONVERT in permissions_for_role(MembershipRole.SALES)
    assert Permission.SHIPMENT_TRANSITION in permissions_for_role(MembershipRole.OPERATIONS)
    assert Permission.PAYMENT_ALLOCATE in permissions_for_role(MembershipRole.FINANCE)
    assert Permission.COMPANY_READ in permissions_for_role(MembershipRole.VIEWER)
    assert Permission.COMPANY_WRITE not in permissions_for_role(MembershipRole.VIEWER)


def test_application_service_permission_guard_is_independent() -> None:
    context = RequestContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        permissions=frozenset(),
        request_id=uuid4(),
    )

    with pytest.raises(ApiProblem) as error:
        context.require(Permission.JOB_READ)

    assert error.value.code == "PERMISSION_DENIED"
