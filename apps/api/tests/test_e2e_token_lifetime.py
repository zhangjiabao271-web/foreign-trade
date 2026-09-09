import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from app.auth.tokens import LocalTestTokenIssuer, LocalTestTokenVerifier, TokenVerificationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from e2e_fixture import (  # noqa: E402
    TOKEN_AUDIENCE,
    TOKEN_ISSUER,
    TOKEN_SECRET,
    issue_browser_token,
)


@pytest.mark.parametrize("role", ["sales", "manager", "operations", "admin"])
def test_browser_fixture_survives_six_minutes_but_still_expires(monkeypatch, role):
    organization_id = uuid4()
    token = issue_browser_token(f"playwright-{role}", organization_id)
    verifier = LocalTestTokenVerifier(
        secret=TOKEN_SECRET, issuer=TOKEN_ISSUER, audience=TOKEN_AUDIENCE
    )
    claims = verifier.verify(token).claims
    assert claims["exp"] - claims["iat"] == 30 * 60

    class Clock(datetime):
        instant = datetime.fromtimestamp(claims["iat"], UTC) + timedelta(minutes=6)

        @classmethod
        def now(cls, tz=None):
            return cls.instant

    monkeypatch.setattr(jwt.api_jwt, "datetime", Clock)
    verified = verifier.verify(token)
    assert verified.subject == f"playwright-{role}"
    assert verified.organization_id == organization_id
    Clock.instant = datetime.fromtimestamp(claims["exp"], UTC)
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_general_local_issuer_keeps_five_minute_default():
    issuer = LocalTestTokenIssuer(secret=TOKEN_SECRET, issuer=TOKEN_ISSUER, audience=TOKEN_AUDIENCE)
    verifier = LocalTestTokenVerifier(
        secret=TOKEN_SECRET, issuer=TOKEN_ISSUER, audience=TOKEN_AUDIENCE
    )
    claims = verifier.verify(issuer.issue(subject="default-unit-test")).claims
    assert claims["exp"] - claims["iat"] == 5 * 60
