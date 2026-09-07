from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker


class UnitOfWork:
    """Explicit transaction boundary; callers must opt in to commit."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork has not been entered")
        return self._session

    def __enter__(self) -> "UnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        return self

    def commit(self) -> None:
        self.session.commit()
        self._committed = True

    def rollback(self) -> None:
        self.session.rollback()

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._committed:
            self.rollback()
        self.session.close()
        self._session = None
