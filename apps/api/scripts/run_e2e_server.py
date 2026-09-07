import os
import sys
from pathlib import Path

import uvicorn
from e2e_processes import record
from sqlalchemy import create_engine

API_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(API_ROOT))

from app.auth.tokens import LocalTestTokenVerifier  # noqa: E402
from app.core.database import create_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from scripts.e2e_fixture import (  # noqa: E402
    TOKEN_AUDIENCE,
    TOKEN_ISSUER,
    TOKEN_SECRET,
    _database_urls,
)


def main() -> None:
    record("api", os.getpid())
    _, database_url = _database_urls()
    app.state.session_factory = create_session_factory(create_engine(database_url))
    app.state.token_verifier = LocalTestTokenVerifier(
        secret=TOKEN_SECRET,
        issuer=TOKEN_ISSUER,
        audience=TOKEN_AUDIENCE,
    )
    uvicorn.run(app, host="127.0.0.1", port=8010, log_level="warning")


if __name__ == "__main__":
    main()
