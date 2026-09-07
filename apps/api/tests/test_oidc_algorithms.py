from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from app.auth.tokens import LogtoTokenVerifier, TokenVerificationError
from app.core.config import Settings
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from pydantic import ValidationError

ISSUER = "https://issuer.example.test/oidc"
AUDIENCE = "https://api.example.test"
pytest_plugins = ("test_quotation_vertical_slice",)


@pytest.fixture(params=["RS256", "ES384"])
def signing(request):
    algorithm = request.param
    if algorithm == "RS256":
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    else:
        private = ec.generate_private_key(ec.SECP384R1())
        public_jwk = jwt.algorithms.ECAlgorithm.to_jwk(private.public_key(), as_dict=True)
    return algorithm, private, {**public_jwk, "kid": "signing-1", "alg": algorithm, "use": "sig"}


def claims():
    return {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "verified-user",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "organization_id": str(uuid4()),
    }


def verifier(monkeypatch, algorithm, keys):
    adapter = LogtoTokenVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url=ISSUER + "/jwks",
        signing_algorithm=algorithm,
    )
    # Real PyJWT JWKS parsing, key selection and signature/claim validation; no HTTP needed.
    monkeypatch.setattr(adapter._jwks_client, "fetch_data", lambda: {"keys": keys})
    return adapter


def test_configured_asymmetric_algorithm_verifies_real_signature(monkeypatch, signing):
    algorithm, private, jwk = signing
    payload = claims()
    token = jwt.encode(payload, private, algorithm=algorithm, headers={"kid": jwk["kid"]})
    result = verifier(monkeypatch, algorithm, [jwk]).verify(token)
    assert result.subject == payload["sub"]
    assert str(result.organization_id) == payload["organization_id"]


@pytest.mark.parametrize(
    "change",
    [
        "issuer",
        "audience",
        "expired",
        "no-expiry",
        "no-subject",
        "bad-organization",
        "signature",
        "kid",
    ],
)
def test_real_signatures_do_not_bypass_claims_or_key_binding(monkeypatch, signing, change):
    algorithm, private, jwk = signing
    payload = claims()
    kid = jwk["kid"]
    if change == "issuer":
        payload["iss"] = "https://attacker.example.test"
    elif change == "audience":
        payload["aud"] = "another-resource"
    elif change == "expired":
        payload["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    elif change == "no-expiry":
        del payload["exp"]
    elif change == "no-subject":
        del payload["sub"]
    elif change == "bad-organization":
        payload["organization_id"] = "not-a-uuid"
    elif change == "kid":
        kid = "unknown-key"
    elif algorithm == "RS256":
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    else:
        private = ec.generate_private_key(ec.SECP384R1())
    token = jwt.encode(payload, private, algorithm=algorithm, headers={"kid": kid})
    with pytest.raises(TokenVerificationError):
        verifier(monkeypatch, algorithm, [jwk]).verify(token)


def test_unconfigured_algorithm_is_rejected_before_jwks_fetch(monkeypatch, signing):
    algorithm, private, jwk = signing
    other = "ES384" if algorithm == "RS256" else "RS256"
    adapter = verifier(monkeypatch, other, [jwk])

    def forbidden_fetch():
        pytest.fail("Untrusted algorithm must not trigger a JWKS fetch")

    monkeypatch.setattr(adapter._jwks_client, "fetch_data", forbidden_fetch)
    token = jwt.encode(claims(), private, algorithm=algorithm, headers={"kid": jwk["kid"]})
    with pytest.raises(TokenVerificationError):
        adapter.verify(token)
    for unsafe in ("HS256", "none"):
        token = jwt.encode(
            claims(),
            "local-test-secret-of-at-least-32-bytes" if unsafe == "HS256" else None,
            algorithm=unsafe,
        )
        with pytest.raises(TokenVerificationError):
            adapter.verify(token)


def test_jwk_declared_algorithm_must_match_configuration(monkeypatch, signing):
    algorithm, private, jwk = signing
    alternate = "RS512" if algorithm == "RS256" else "ES256"
    token = jwt.encode(claims(), private, algorithm=algorithm, headers={"kid": jwk["kid"]})
    with pytest.raises(TokenVerificationError):
        verifier(monkeypatch, algorithm, [{**jwk, "alg": alternate}]).verify(token)


@pytest.mark.parametrize("algorithm", ["none", "HS256", "RS512", "ES256", "RS256,ES384", ""])
def test_unsupported_policy_is_rejected_at_startup(algorithm):
    with pytest.raises(ValidationError):
        Settings(oidc_signing_algorithm=algorithm)
    with pytest.raises(ValueError):
        LogtoTokenVerifier(
            issuer=ISSUER, audience=AUDIENCE, jwks_url=ISSUER + "/jwks", signing_algorithm=algorithm
        )


def test_runtime_factory_uses_explicit_signing_policy(monkeypatch):
    from app.auth import dependencies

    monkeypatch.setattr(
        dependencies, "get_settings", lambda: Settings(oidc_signing_algorithm="ES384")
    )
    dependencies._default_token_verifier.cache_clear()
    try:
        assert dependencies._default_token_verifier()._signing_algorithm == "ES384"
    finally:
        dependencies._default_token_verifier.cache_clear()


def test_es384_rejects_wrong_curve_before_decoding(monkeypatch):
    private = ec.generate_private_key(ec.SECP384R1())
    wrong = ec.generate_private_key(ec.SECP256R1())
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(wrong.public_key(), as_dict=True)
    jwk.update(kid="wrong-curve", alg="ES384", use="sig")
    token = jwt.encode(claims(), private, algorithm="ES384", headers={"kid": "wrong-curve"})
    adapter = verifier(monkeypatch, "ES384", [jwk])

    def forbidden_decode(*args, **kwargs):
        pytest.fail("A mismatched curve must be rejected before JWT decode")

    monkeypatch.setattr(jwt, "decode", forbidden_decode)
    with pytest.raises(TokenVerificationError, match="P-384"):
        adapter.verify(token)


@pytest.mark.integration
def test_asymmetric_runtime_tokens_keep_membership_and_organization_gates(
    monkeypatch, signing, quotation_fixture
):
    from app.main import app

    f = quotation_fixture
    algorithm, private, jwk = signing
    # The database fixture owns and removes this override during teardown.
    app.state.token_verifier = verifier(monkeypatch, algorithm, [jwk])

    def headers(subject, organization):
        payload = claims() | {"sub": subject}
        del payload["organization_id"]
        token = jwt.encode(payload, private, algorithm=algorithm, headers={"kid": jwk["kid"]})
        return {"Authorization": f"Bearer {token}", "X-Organization-ID": str(organization)}

    valid = headers("quotation-sales", f.organization_a)
    assert f.client.get("/api/v1/me/context", headers=valid).status_code == 200
    organizations = f.client.get("/api/v1/me/organizations", headers=valid)
    assert organizations.status_code == 200
    assert str(f.organization_a) in organizations.text
    assert str(f.organization_b) not in organizations.text
    assert (
        f.client.get(
            "/api/v1/me/context", headers=headers("quotation-sales", f.organization_b)
        ).status_code
        == 403
    )
    assert (
        f.client.get(
            "/api/v1/me/context", headers=headers("unmapped-user", f.organization_a)
        ).status_code
        == 403
    )
