from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.assistant_queries import CompanyAssistantQueries
from app.sales.assistant_queries import OrderAssistantQueries


class OrderArgument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: UUID


class SearchArgument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    term: str = Field(min_length=2, max_length=80)


class ApplicationTools:
    schemas: ClassVar[dict[str, type[BaseModel]]] = {
        "read_order": OrderArgument,
        "order_timeline": OrderArgument,
        "order_profit": OrderArgument,
        "search_companies": SearchArgument,
    }

    @classmethod
    def definitions(cls, intent: str) -> list[dict[str, object]]:
        names = ["search_companies"] if intent == "SEARCH" else ["read_order", "order_timeline"]
        if intent == "PROFIT":
            names.append("order_profit")
        return [
            {
                "type": "function",
                "name": name,
                "description": f"Read bounded authorized {name} facts.",
                "parameters": cls.schemas[name].model_json_schema(),
                "strict": True,
            }
            for name in names
        ]

    @classmethod
    def execute(
        cls,
        session: Session,
        context: RequestContext,
        *,
        name: str,
        arguments: dict[str, object],
        intent: str,
        subject_id: UUID | None,
        search_term: str | None,
    ) -> dict[str, object]:
        context.require(Permission.AI_RUN)
        if name not in {tool["name"] for tool in cls.definitions(intent)}:
            raise ApiProblem(
                403, "AI_TOOL_DENIED", "Tool denied", "This tool is not allowed for this intent."
            )
        if name == "search_companies":
            data = SearchArgument.model_validate(arguments)
            if data.term != search_term:
                raise ApiProblem(
                    403, "AI_SCOPE_DENIED", "Scope denied", "Use the requested search term."
                )
            return CompanyAssistantQueries(session).search(context, data.term)
        order = OrderArgument.model_validate(arguments)
        if order.order_id != subject_id:
            raise ApiProblem(
                404, "SALES_ORDER_NOT_FOUND", "Order not found", "Order not found in this run."
            )
        queries = OrderAssistantQueries(session)
        if name == "order_timeline":
            return queries.timeline(context, order.order_id)
        return queries.snapshot(context, order.order_id, profit=name == "order_profit")
