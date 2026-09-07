from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt import PyJWKClient


class TokenVerificationError(ValueError):
    """A bearer token failed cryptographic or claims validation."""


@dataclass(frozen=True, slots=True)
class VerifiedToken:
    subject: str
    organization_id: UUID | None
    claims: Mapping[str, Any]


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedToken: ...


def _verified_token(claims: Mapping[str, Any]) -> VerifiedToken:
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenVerificationError("Token subject is missing")

    raw_organization_id = claims.get("organization_id")
    organization_id: UUID | None = None
    if raw_organization_id is not None:
        try:
            organization_id = UUID(str(raw_organization_id))
        except ValueError as error:
            raise TokenVerificationError("Token organization is invalid") from error
    return VerifiedToken(subject=subject, organization_id=organization_id, claims=claims)


class LogtoTokenVerifier:
    """PyJWT-backed Logto/OIDC adapter using the issuer's JWKS endpoint."""

    def __init__(
        self, *, issuer: str, audience: str, jwks_url: str, signing_algorithm: str = "RS256"
    ) -> None:
        if signing_algorithm not in {"RS256", "ES384"}:
            raise ValueError("Unsupported OIDC signing algorithm")
        self._issuer = issuer
        self._audience = audience
        self._signing_algorithm = signing_algorithm
        self._jwks_client = PyJWKClient(jwks_url)

    def verify(self, token: str) -> VerifiedToken:
        try:
            # The header may only be compared to trusted configuration, never select policy.
            if jwt.get_unverified_header(token).get("alg") != self._signing_algorithm:
                raise TokenVerificationError("Token signing algorithm is not allowed")
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            if signing_key.algorithm_name != self._signing_algorithm:
                raise TokenVerificationError("Signing key algorithm does not match policy")
            key = signing_key.key
            if self._signing_algorithm == "RS256":
                if not isinstance(key, rsa.RSAPublicKey):
                    raise TokenVerificationError("Expected an RSA public key")
            elif not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(
                key.curve, ec.SECP384R1
            ):
                raise TokenVerificationError("Expected a P-384 public key")
            claims = jwt.decode(
                token,
                key,
                algorithms=[self._signing_algorithm],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as error:
            raise TokenVerificationError("Token validation failed") from error
        return _verified_token(claims)


class LocalTestTokenIssuer:
    """Deterministic local issuer for tests; never selected by runtime configuration."""

    def __init__(self, *, secret: str, issuer: str, audience: str) -> None:
        self._secret = secret
        self.issuer = issuer
        self.audience = audience

    def issue(
        self,
        *,
        subject: str,
        organization_id: UUID | None = None,
        expires_in: timedelta = timedelta(minutes=5),
        issuer: str | None = None,
        audience: str | None = None,
    ) -> str:
        now = datetime.now(UTC)
        claims: dict[str, object] = {
            "sub": subject,
            "iss": issuer or self.issuer,
            "aud": audience or self.audience,
            "iat": now,
            "exp": now + expires_in,
        }
        if organization_id is not None:
            claims["organization_id"] = str(organization_id)
        return jwt.encode(claims, self._secret, algorithm="HS256")


class LocalTestTokenVerifier:
    def __init__(self, *, secret: str, issuer: str, audience: str) -> None:
        self._secret = secret
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str) -> VerifiedToken:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as error:
            raise TokenVerificationError("Token validation failed") from error
        return _verified_token(claims)
