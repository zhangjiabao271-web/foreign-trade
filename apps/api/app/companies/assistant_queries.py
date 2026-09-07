from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.companies.models import Company


class CompanyAssistantQueries:
    def __init__(self, session: Session) -> None:
        self.session = session

    def search(self, context: RequestContext, term: str) -> dict[str, object]:
        context.require(Permission.COMPANY_READ)
        name = func.coalesce(Company.name, "")
        rows = self.session.scalars(
            select(Company)
            .where(
                Company.organization_id == context.organization_id,
                Company.deleted_at.is_(None),
                or_(
                    name.icontains(term, autoescape=True),
                    func.to_tsvector("simple", name).op("@@")(func.plainto_tsquery("simple", term)),
                ),
            )
            .order_by(Company.name, Company.id)
            .limit(11)
        ).all()
        return {
            "items": [
                {
                    "source": {"type": "company", "id": str(row.id), "version": row.version},
                    "name": row.name,
                }
                for row in rows[:10]
            ],
            "has_more": len(rows) > 10,
        }
