from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.platform.models import DocumentSequence


def next_document_number(
    session: Session,
    context: RequestContext,
    document_type: str,
    prefix: str,
) -> str:
    year = datetime.now(UTC).year
    statement = (
        insert(DocumentSequence)
        .values(
            organization_id=context.organization_id,
            created_by=context.user_id,
            updated_by=context.user_id,
            document_type=document_type,
            calendar_year=year,
            next_value=2,
        )
        .on_conflict_do_update(
            index_elements=["organization_id", "document_type", "calendar_year"],
            set_={"next_value": DocumentSequence.next_value + 1, "updated_by": context.user_id},
        )
        .returning(DocumentSequence.next_value)
    )
    value = session.execute(statement).scalar_one() - 1
    return f"{prefix}-{year}-{value:06d}"
