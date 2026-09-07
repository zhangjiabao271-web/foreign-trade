from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.catalog.models import Product
from app.core.unit_of_work import UnitOfWork
from app.crm.enums import OpportunityStatus
from app.crm.models import Opportunity
from app.crm.opportunity_services import advance_from_evidence
from app.identity.calendar import organization_timezone
from app.inquiries.enums import InquiryStatus
from app.inquiries.models import Inquiry
from app.platform.idempotency import begin_command, complete_command
from app.platform.numbering import next_document_number
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.enums import QuotationVersionStatus
from app.sales.models import Quotation, QuotationItem, QuotationVersion
from app.sales.quotation_projections import (
    quotation_list_item,
    quotation_response,
    version_response,
)
from app.sales.repositories import QuotationRepository
from app.sales.schemas import (
    CustomerReviewCommand,
    QuotationCreate,
    QuotationListItem,
    QuotationResponse,
    QuotationRevisionCreate,
    QuotationStateCommand,
    QuotationVersionResponse,
)
from app.sales.state_commands import begin_state_command
from app.work.models import Activity

MONEY_QUANTUM = Decimal("0.0001")
RATE_QUANTUM = Decimal("0.00000001")


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def quantize_rate(value: Decimal) -> Decimal:
    return value.quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)


def quotation_not_found() -> ApiProblem:
    return ApiProblem(
        404,
        "QUOTATION_NOT_FOUND",
        "Quotation not found",
        "The quotation was not found.",
    )


def require_cost_authority(context: RequestContext, data: dict[str, object]) -> None:
    items = data.get("items")
    protected = {"unit_cost", "cost_currency", "cost_exchange_rate", "allocated_cost"}
    if isinstance(items, list) and any(
        isinstance(item, dict) and protected.intersection(item) for item in items
    ):
        context.require(Permission.PROFIT_READ)


def cost_preparation_required() -> ApiProblem:
    return ApiProblem(
        409,
        "COST_PREPARATION_REQUIRED",
        "Cost preparation required",
        "成本换算快照尚未准备完整，请经理核实成本币种和换算率后再创建或改版。",
    )


def current_quotation_response(
    repository: QuotationRepository, context: RequestContext, quotation: Quotation
) -> QuotationResponse:
    versions = repository.versions(
        organization_id=context.organization_id, quotation_id=quotation.id
    )
    current = next((version for version in versions if version.is_current), None)
    if current is None:
        raise RuntimeError("Quotation invariant violated: current version is missing")
    items = {
        version.id: repository.items(organization_id=context.organization_id, version_id=version.id)
        for version in versions
    }
    return quotation_response(context, quotation, current, versions, items)


class QuotationQueryService:
    def __init__(self, repository: QuotationRepository) -> None:
        self._repository = repository

    def list(
        self,
        context: RequestContext,
        *,
        status: QuotationVersionStatus | None,
        limit: int,
        cursor: UUID | None = None,
    ) -> Sequence[QuotationListItem]:
        context.require(Permission.QUOTATION_READ)
        return [
            quotation_list_item(context, quotation, version)
            for quotation, version in self._repository.list_with_current(
                organization_id=context.organization_id, status=status, limit=limit, cursor=cursor
            )
        ]

    def get(self, context: RequestContext, quotation_id: UUID) -> QuotationResponse:
        context.require(Permission.QUOTATION_READ)
        quotation = self._repository.get(
            organization_id=context.organization_id, record_id=quotation_id
        )
        if quotation is None:
            raise quotation_not_found()
        return current_quotation_response(self._repository, context, quotation)


class QuotationCommandService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        audit_recorder: AuditRecorder | None = None,
        outbox_recorder: OutboxRecorder | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._audit_recorder = audit_recorder or AuditRecorder()
        self._outbox_recorder = outbox_recorder or OutboxRecorder()

    def create(
        self, context: RequestContext, data: dict[str, object], *, key: str | None = None
    ) -> QuotationResponse:
        context.require(Permission.QUOTATION_WRITE)
        require_cost_authority(context, data)
        data = QuotationCreate.model_validate(data).model_dump(exclude_unset=True)
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            command = begin_command(
                session,
                context,
                scope="quotation.create",
                key=key if key is not None else str(uuid4()),
                payload=data,
            )
            if command.resource_id is not None:
                repository = QuotationRepository(session)
                original = repository.get_for_update(
                    organization_id=context.organization_id, quotation_id=command.resource_id
                )
                if original is None:
                    raise quotation_not_found()
                result = current_quotation_response(repository, context, original)
                unit_of_work.commit()
                return result
            inquiry = session.scalar(
                select(Inquiry)
                .where(
                    Inquiry.organization_id == context.organization_id,
                    Inquiry.id == data["inquiry_id"],
                    Inquiry.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if inquiry is None:
                raise ApiProblem(
                    404, "INQUIRY_NOT_FOUND", "Inquiry not found", "The inquiry was not found."
                )
            existing = session.scalar(
                select(Quotation).where(
                    Quotation.organization_id == context.organization_id,
                    Quotation.inquiry_id == inquiry.id,
                    Quotation.deleted_at.is_(None),
                )
            )
            if existing is not None:
                raise ApiProblem(
                    409,
                    "INQUIRY_ALREADY_QUOTED",
                    "Inquiry already quoted",
                    "Create a revision on the existing quotation.",
                )
            opportunity = session.scalar(
                select(Opportunity)
                .where(
                    Opportunity.organization_id == context.organization_id,
                    Opportunity.id == inquiry.opportunity_id,
                    Opportunity.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if opportunity is None:
                raise ApiProblem(
                    404,
                    "OPPORTUNITY_NOT_FOUND",
                    "Opportunity not found",
                    "The opportunity was not found.",
                )
            if opportunity.status not in {OpportunityStatus.INQUIRY, OpportunityStatus.QUOTING}:
                raise self._invalid_state("Opportunity must be INQUIRY before quoting.")

            items_data = data.pop("items")
            if not isinstance(items_data, list):
                raise TypeError("Quotation items must be a list")
            quotation = Quotation(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                quotation_number=self._next_number(session, context),
                inquiry_id=inquiry.id,
                opportunity_id=opportunity.id,
                company_id=inquiry.company_id,
            )
            session.add(quotation)
            session.flush()
            version, items = self._create_version(
                session,
                context,
                quotation_id=quotation.id,
                version_number=1,
                values=data,
                items_data=items_data,
            )
            inquiry.status = InquiryStatus.QUOTING
            inquiry.updated_by = context.user_id
            advance_from_evidence(
                session, context, opportunity.id, event="quotation", evidence_id=quotation.id
            )
            self._record_command(
                session,
                context,
                quotation,
                version,
                action="quotation.created",
                summary=f"Quotation {quotation.quotation_number} V1 created",
                before=None,
                after={"status": version.status, "version_number": 1},
            )
            complete_command(command, quotation.id, "quotation")
            unit_of_work.commit()
            return quotation_response(context, quotation, version, [version], {version.id: items})

    def revise(
        self,
        context: RequestContext,
        quotation_id: UUID,
        changes: dict[str, object],
        *,
        key: str,
    ) -> QuotationVersionResponse:
        context.require(Permission.QUOTATION_WRITE)
        request = QuotationRevisionCreate.model_validate(changes)
        require_cost_authority(context, changes)
        changes = request.model_dump(exclude_unset=True, exclude={"expected_version_id"})
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            quotation, current = self._locked_current(session, context, quotation_id)
            command = begin_command(
                session,
                context,
                scope="quotation.revise",
                key=key,
                payload={
                    "quotation_id": str(quotation_id),
                    **request.model_dump(exclude_unset=True),
                },
            )
            if command.resource_id is not None:
                original = session.scalar(
                    select(QuotationVersion).where(
                        QuotationVersion.organization_id == context.organization_id,
                        QuotationVersion.quotation_id == quotation_id,
                        QuotationVersion.id == command.resource_id,
                        QuotationVersion.deleted_at.is_(None),
                    )
                )
                if original is None:
                    raise quotation_not_found()
                items = QuotationRepository(session).items(
                    organization_id=context.organization_id, version_id=original.id
                )
                unit_of_work.commit()
                return version_response(context, original, items)
            if (
                request.expected_version_id is not None
                and current.id != request.expected_version_id
            ):
                raise ApiProblem(
                    409,
                    "VERSION_CONFLICT",
                    "Version conflict",
                    "报价已有新版本，请刷新后重新检查改版内容。",
                )
            if current.status == QuotationVersionStatus.ACCEPTED:
                raise self._invalid_state("An accepted quotation cannot be revised.")

            old_items = QuotationRepository(session).items(
                organization_id=context.organization_id, version_id=current.id
            )
            supplied_items = changes.pop("items", None)
            if supplied_items is None:
                items_data: list[dict[str, object]] = [
                    {**self._snapshot_input(item), "source_item_id": item.id} for item in old_items
                ]
            elif isinstance(supplied_items, list):
                items_data = supplied_items
            else:
                raise TypeError("Quotation items must be a list")

            old_by_id = {item.id: item for item in old_items}
            source_items: dict[int, QuotationItem] = {}
            explicit_rates = {
                index + 1
                for index, item in enumerate(supplied_items or [])
                if isinstance(item, dict) and "cost_exchange_rate" in item
            }
            for index, item_data in enumerate(items_data):
                source_id = item_data.get("source_item_id")
                if source_id is None:
                    continue
                source = old_by_id.get(UUID(str(source_id)))
                if source is None:
                    raise ApiProblem(
                        404,
                        "QUOTATION_ITEM_NOT_FOUND",
                        "Quotation item not found",
                        "The source line is not in this quotation's current version.",
                    )
                if source.product_id != UUID(str(item_data["product_id"])):
                    raise ApiProblem(
                        409,
                        "SOURCE_ITEM_PRODUCT_MISMATCH",
                        "Source product mismatch",
                        "A copied line must retain its source product; "
                        "add a new line to change products.",
                    )
                source_items[index + 1] = source
                items_data[index] = {**self._snapshot_input(source), **item_data}

            version_values: dict[str, object] = {
                "currency_code": current.currency_code,
                "base_currency_code": current.base_currency_code,
                "exchange_rate": current.exchange_rate,
                "valid_until": current.valid_until,
                "payment_terms": current.payment_terms,
                "delivery_terms": current.delivery_terms,
            }
            version_values.update(changes)
            for number, source in source_items.items():
                item_data = items_data[number - 1]
                currency = item_data.get("cost_currency") or source.cost_currency
                if (
                    version_values["currency_code"] != current.currency_code
                    or currency != source.cost_currency
                ) and number not in explicit_rates:
                    if currency != version_values["currency_code"]:
                        raise cost_preparation_required()
                    item_data["cost_exchange_rate"] = Decimal("1")
            previous_status = current.status
            current.is_current = False
            current.status = QuotationVersionStatus.SUPERSEDED
            current.updated_by = context.user_id
            version, items = self._create_version(
                session,
                context,
                quotation_id=quotation.id,
                version_number=current.version_number + 1,
                values=version_values,
                items_data=items_data,
                source_items=source_items,
            )
            self._record_command(
                session,
                context,
                quotation,
                version,
                action="quotation.revised",
                summary=f"Quotation revised to V{version.version_number}",
                before={"version_id": str(current.id), "status": previous_status},
                after={
                    "version_id": str(version.id),
                    "status": version.status,
                    "source_items": [
                        {"line_number": number, "source_item_id": str(item.id)}
                        for number, item in source_items.items()
                    ],
                },
            )
            complete_command(command, version.id, "quotation_version")
            unit_of_work.commit()
            return version_response(context, version, items)

    def submit(
        self,
        context: RequestContext,
        quotation_id: UUID,
        request: QuotationStateCommand,
        *,
        key: str,
    ) -> QuotationVersionResponse:
        context.require(Permission.QUOTATION_SUBMIT)
        return self._transition(
            context,
            quotation_id,
            request=request,
            key=key,
            expected={QuotationVersionStatus.DRAFT},
            target=QuotationVersionStatus.INTERNAL_REVIEW,
            action="quotation.submitted",
            summary="Quotation submitted for internal review",
            timestamp_field="submitted_at",
        )

    def approve(
        self,
        context: RequestContext,
        quotation_id: UUID,
        request: QuotationStateCommand,
        *,
        key: str,
    ) -> QuotationVersionResponse:
        context.require(Permission.QUOTATION_APPROVE)
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            quotation, current = self._locked_current(session, context, quotation_id)
            command, replay = begin_state_command(
                session, context, quotation, current, request, action="approved", key=key
            )
            if replay is not None:
                unit_of_work.commit()
                return replay
            if current.status != QuotationVersionStatus.INTERNAL_REVIEW:
                raise self._invalid_state("Quotation must be in INTERNAL_REVIEW before approval.")
            if current.approved_at is not None:
                complete_command(command, current.id, "quotation_version")
                items = QuotationRepository(session).items(
                    organization_id=context.organization_id, version_id=current.id
                )
                unit_of_work.commit()
                return version_response(context, current, items)
            now = datetime.now(UTC)
            current.approved_at = now
            current.approved_by = context.user_id
            current.updated_by = context.user_id
            complete_command(command, current.id, "quotation_version")
            self._record_command(
                session,
                context,
                quotation,
                current,
                action="quotation.approved",
                summary="Quotation approved by manager",
                before={"approved_at": None},
                after={"approved_at": now.isoformat(), "approved_by": str(context.user_id)},
            )
            items = QuotationRepository(session).items(
                organization_id=context.organization_id, version_id=current.id
            )
            unit_of_work.commit()
            return version_response(context, current, items)

    def send(
        self,
        context: RequestContext,
        quotation_id: UUID,
        request: QuotationStateCommand,
        *,
        key: str,
    ) -> QuotationVersionResponse:
        context.require(Permission.QUOTATION_SEND)
        return self._transition(
            context,
            quotation_id,
            request=request,
            key=key,
            expected={QuotationVersionStatus.INTERNAL_REVIEW},
            target=QuotationVersionStatus.SENT,
            action="quotation.sent",
            summary="Approved quotation sent to customer",
            timestamp_field="sent_at",
            require_approval=True,
        )

    def mark_customer_review(
        self, context: RequestContext, quotation_id: UUID, data: dict[str, object], *, key: str
    ) -> UUID:
        context.require(Permission.QUOTATION_SEND)
        request = CustomerReviewCommand.model_validate(data)
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            quotation, current = self._locked_current(session, context, quotation_id)
            command = begin_command(
                session,
                context,
                scope="quotation.customer_review_started",
                key=key,
                payload={"quotation_id": str(quotation_id), **request.model_dump()},
            )
            if command.resource_id is not None:
                unit_of_work.commit()
                return command.resource_id
            if current.id != request.expected_version_id:
                raise ApiProblem(
                    409,
                    "VERSION_CONFLICT",
                    "Version conflict",
                    "Refresh the quotation before recording customer review.",
                )
            if current.status != QuotationVersionStatus.SENT:
                raise self._invalid_state("Only a SENT quotation can enter customer review.")
            current.status = QuotationVersionStatus.CUSTOMER_REVIEW
            current.updated_by = context.user_id
            current.version += 1
            self._record_command(
                session,
                context,
                quotation,
                current,
                action="quotation.customer_review_started",
                summary="已确认客户正在审阅报价",
                before={"status": QuotationVersionStatus.SENT},
                after={"status": current.status},
                reason=request.reason,
            )
            complete_command(command, current.id, "quotation_version")
            unit_of_work.commit()
            return current.id

    def accept(
        self,
        context: RequestContext,
        quotation_id: UUID,
        request: QuotationStateCommand,
        *,
        key: str,
    ) -> QuotationVersionResponse:
        context.require(Permission.QUOTATION_ACCEPT)
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            quotation, current = self._locked_current(session, context, quotation_id)
            command, replay = begin_state_command(
                session, context, quotation, current, request, action="accepted", key=key
            )
            if replay is not None:
                unit_of_work.commit()
                return replay
            repository = QuotationRepository(session)
            if quotation.accepted_version_id is not None:
                accepted = session.scalar(
                    select(QuotationVersion).where(
                        QuotationVersion.organization_id == context.organization_id,
                        QuotationVersion.id == quotation.accepted_version_id,
                    )
                )
                if accepted is None:
                    raise RuntimeError("Quotation invariant violated: accepted version is missing")
                items = repository.items(
                    organization_id=context.organization_id, version_id=accepted.id
                )
                complete_command(command, accepted.id, "quotation_version")
                unit_of_work.commit()
                return version_response(context, accepted, items)
            if current.status not in {
                QuotationVersionStatus.SENT,
                QuotationVersionStatus.CUSTOMER_REVIEW,
            }:
                raise self._invalid_state("Quotation must be SENT before it can be accepted.")

            opportunity = session.scalar(
                select(Opportunity)
                .where(
                    Opportunity.organization_id == context.organization_id,
                    Opportunity.id == quotation.opportunity_id,
                    Opportunity.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if opportunity is None:
                raise ApiProblem(
                    404,
                    "OPPORTUNITY_NOT_FOUND",
                    "Opportunity not found",
                    "The opportunity was not found.",
                )
            timezone = organization_timezone(session, context.organization_id)
            now = datetime.now(UTC)
            if current.valid_until < now.astimezone(timezone).date():
                raise ApiProblem(
                    409,
                    "QUOTATION_VALIDITY_ENDED",
                    "Quotation validity ended",
                    "报价已超过组织当地日期的有效期，请创建修订版并重新审核发送。",
                )
            previous = current.status
            previous_opportunity_status = opportunity.status
            current.status = QuotationVersionStatus.ACCEPTED
            current.accepted_at = now
            current.updated_by = context.user_id
            quotation.accepted_version_id = current.id
            quotation.updated_by = context.user_id
            complete_command(command, current.id, "quotation_version")
            advance_from_evidence(
                session, context, opportunity.id, event="accepted", evidence_id=current.id
            )
            self._record_command(
                session,
                context,
                quotation,
                current,
                action="quotation.accepted",
                summary="Quotation accepted; opportunity won",
                before={
                    "status": previous,
                    "opportunity_status": previous_opportunity_status,
                },
                after={"status": current.status, "opportunity_status": OpportunityStatus.WON},
            )
            items = repository.items(organization_id=context.organization_id, version_id=current.id)
            unit_of_work.commit()
            return version_response(context, current, items)

    def reject(
        self,
        context: RequestContext,
        quotation_id: UUID,
        request: QuotationStateCommand,
        *,
        key: str,
    ) -> QuotationVersionResponse:
        context.require(Permission.QUOTATION_ACCEPT)
        return self._transition(
            context,
            quotation_id,
            request=request,
            key=key,
            expected={QuotationVersionStatus.SENT, QuotationVersionStatus.CUSTOMER_REVIEW},
            target=QuotationVersionStatus.REJECTED,
            action="quotation.rejected",
            summary="Quotation rejected by customer",
        )

    def expire(
        self,
        context: RequestContext,
        quotation_id: UUID,
        request: QuotationStateCommand,
        *,
        key: str,
    ) -> QuotationVersionResponse:
        context.require(Permission.QUOTATION_WRITE)
        return self._transition(
            context,
            quotation_id,
            request=request,
            key=key,
            expected={
                QuotationVersionStatus.DRAFT,
                QuotationVersionStatus.INTERNAL_REVIEW,
                QuotationVersionStatus.SENT,
                QuotationVersionStatus.CUSTOMER_REVIEW,
            },
            target=QuotationVersionStatus.EXPIRED,
            action="quotation.expired",
            summary="Quotation expired",
        )

    def _transition(
        self,
        context: RequestContext,
        quotation_id: UUID,
        *,
        request: QuotationStateCommand,
        key: str,
        expected: set[QuotationVersionStatus],
        target: QuotationVersionStatus,
        action: str,
        summary: str,
        timestamp_field: str | None = None,
        require_approval: bool = False,
    ) -> QuotationVersionResponse:
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            quotation, current = self._locked_current(session, context, quotation_id)
            command, replay = begin_state_command(
                session,
                context,
                quotation,
                current,
                request,
                action=action.removeprefix("quotation."),
                key=key,
            )
            if replay is not None:
                unit_of_work.commit()
                return replay
            if current.status not in expected:
                raise self._invalid_state(
                    f"Quotation cannot move from {current.status} to {target}."
                )
            if require_approval and current.approved_at is None:
                raise self._invalid_state("Quotation must be approved before it can be sent.")
            previous = current.status
            current.status = target
            current.updated_by = context.user_id
            if timestamp_field is not None:
                setattr(current, timestamp_field, datetime.now(UTC))
            complete_command(command, current.id, "quotation_version")
            self._record_command(
                session,
                context,
                quotation,
                current,
                action=action,
                summary=summary,
                before={"status": previous},
                after={"status": target},
            )
            items = QuotationRepository(session).items(
                organization_id=context.organization_id, version_id=current.id
            )
            unit_of_work.commit()
            return version_response(context, current, items)

    @staticmethod
    def _snapshot_input(item: QuotationItem) -> dict[str, object]:
        return {
            "product_id": item.product_id,
            "description": item.description_snapshot,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "unit_cost": item.unit_cost,
            "cost_currency": item.cost_currency,
            "cost_exchange_rate": item.cost_exchange_rate,
            "tax_amount": item.tax_amount,
            "freight_amount": item.freight_amount,
            "allocated_cost": item.allocated_cost,
        }

    def _create_version(
        self,
        session: Session,
        context: RequestContext,
        *,
        quotation_id: UUID,
        version_number: int,
        values: dict[str, object],
        items_data: list[dict[str, object]],
        source_items: Mapping[int, QuotationItem] | None = None,
    ) -> tuple[QuotationVersion, list[QuotationItem]]:
        sources = source_items or {}
        new_items = [
            item for number, item in enumerate(items_data, start=1) if number not in sources
        ]
        products = self._products_by_id(session, context.organization_id, new_items)
        version = QuotationVersion(
            organization_id=context.organization_id,
            created_by=context.user_id,
            updated_by=context.user_id,
            quotation_id=quotation_id,
            version_number=version_number,
            currency_code=str(values["currency_code"]).upper(),
            base_currency_code=str(values["base_currency_code"]).upper(),
            exchange_rate=quantize_rate(Decimal(str(values["exchange_rate"]))),
            valid_until=values["valid_until"],
            payment_terms=values.get("payment_terms"),
            delivery_terms=values.get("delivery_terms"),
            subtotal=Decimal("0"),
            tax_amount=Decimal("0"),
            freight_amount=Decimal("0"),
            total=Decimal("0"),
            total_cost=Decimal("0"),
            gross_profit=Decimal("0"),
            gross_margin=Decimal("0"),
        )
        session.add(version)
        session.flush()

        items: list[QuotationItem] = []
        for line_number, item_data in enumerate(items_data, start=1):
            product_id = item_data["product_id"]
            if not isinstance(product_id, UUID):
                product_id = UUID(str(product_id))
            source = sources.get(line_number)
            if source is not None:
                sku = source.sku_snapshot
                unit = source.unit_snapshot
                description = source.description_snapshot
                default_cost = source.unit_cost
                default_currency = source.cost_currency
            else:
                product = products[product_id]
                sku = product.sku
                unit = product.unit
                description = product.description or product.name
                default_cost = product.standard_cost
                default_currency = product.cost_currency
            quantity = quantize_money(Decimal(str(item_data["quantity"])))
            unit_price = quantize_money(Decimal(str(item_data["unit_price"])))
            supplied_unit_cost = item_data.get("unit_cost")
            unit_cost = quantize_money(
                Decimal(str(default_cost if supplied_unit_cost is None else supplied_unit_cost))
            )
            cost_currency = str(item_data.get("cost_currency") or default_currency).upper()
            if (
                item_data.get("cost_exchange_rate") is None
                and cost_currency != version.currency_code
            ):
                raise cost_preparation_required()
            cost_exchange_rate = quantize_rate(
                Decimal(str(item_data.get("cost_exchange_rate") or Decimal("1")))
            )
            tax_amount = quantize_money(Decimal(str(item_data.get("tax_amount", 0))))
            freight_amount = quantize_money(Decimal(str(item_data.get("freight_amount", 0))))
            allocated_cost = quantize_money(Decimal(str(item_data.get("allocated_cost") or 0)))
            line_subtotal = quantize_money(quantity * unit_price)
            line_total = quantize_money(line_subtotal + tax_amount + freight_amount)
            line_cost = quantize_money(quantity * unit_cost * cost_exchange_rate + allocated_cost)
            item = QuotationItem(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                quotation_version_id=version.id,
                line_number=line_number,
                product_id=product_id,
                sku_snapshot=sku,
                description_snapshot=str(item_data.get("description") or description),
                unit_snapshot=unit,
                quantity=quantity,
                unit_price=unit_price,
                unit_cost=unit_cost,
                cost_currency=cost_currency,
                cost_exchange_rate=cost_exchange_rate,
                tax_amount=tax_amount,
                freight_amount=freight_amount,
                allocated_cost=allocated_cost,
                line_subtotal=line_subtotal,
                line_total=line_total,
                line_cost=line_cost,
                line_gross_profit=quantize_money(line_total - line_cost),
            )
            session.add(item)
            items.append(item)

        version.subtotal = quantize_money(sum((item.line_subtotal for item in items), Decimal("0")))
        version.tax_amount = quantize_money(sum((item.tax_amount for item in items), Decimal("0")))
        version.freight_amount = quantize_money(
            sum((item.freight_amount for item in items), Decimal("0"))
        )
        version.total = quantize_money(sum((item.line_total for item in items), Decimal("0")))
        version.total_cost = quantize_money(sum((item.line_cost for item in items), Decimal("0")))
        version.gross_profit = quantize_money(version.total - version.total_cost)
        version.gross_margin = (
            quantize_money(version.gross_profit / version.total)
            if version.total != 0
            else Decimal("0.0000")
        )
        session.flush()
        return version, items

    @staticmethod
    def _products_by_id(
        session: Session, organization_id: UUID, items_data: list[dict[str, object]]
    ) -> dict[UUID, Product]:
        product_ids = {UUID(str(item["product_id"])) for item in items_data}
        if not product_ids:
            return {}
        products = session.scalars(
            select(Product).where(
                Product.organization_id == organization_id,
                Product.id.in_(product_ids),
                Product.deleted_at.is_(None),
            )
        ).all()
        by_id = {product.id: product for product in products}
        if by_id.keys() != product_ids:
            raise ApiProblem(
                404,
                "PRODUCT_NOT_FOUND",
                "Product not found",
                "One or more products were not found.",
            )
        return by_id

    @staticmethod
    def _next_number(session: Session, context: RequestContext) -> str:
        return next_document_number(session, context, "QUOTATION", "Q")

    @staticmethod
    def _locked_current(
        session: Session, context: RequestContext, quotation_id: UUID
    ) -> tuple[Quotation, QuotationVersion]:
        repository = QuotationRepository(session)
        quotation = repository.get_for_update(
            organization_id=context.organization_id, quotation_id=quotation_id
        )
        if quotation is None:
            raise quotation_not_found()
        current = repository.current_version_for_update(
            organization_id=context.organization_id, quotation_id=quotation_id
        )
        if current is None:
            raise RuntimeError("Quotation invariant violated: current version is missing")
        return quotation, current

    def _record_command(
        self,
        session: Session,
        context: RequestContext,
        quotation: Quotation,
        version: QuotationVersion,
        *,
        action: str,
        summary: str,
        before: dict[str, object] | None,
        after: dict[str, object],
        reason: str | None = None,
    ) -> None:
        session.add(
            Activity(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                subject_type="quotation",
                subject_id=quotation.id,
                activity_type=action,
                summary=summary,
                details={
                    "version_id": str(version.id),
                    "version_number": version.version_number,
                    **({"reason": reason} if reason is not None else {}),
                },
                correlation_id=context.request_id,
            )
        )
        self._audit_recorder.record(
            session,
            context,
            action=action,
            target_type="quotation_version",
            target_id=version.id,
            before=before,
            after=after,
            reason=reason,
        )
        self._outbox_recorder.record(
            session,
            context,
            DomainEvent(
                f"{action}.v1",
                "quotation",
                quotation.id,
                {
                    "quotation_id": str(quotation.id),
                    "quotation_version_id": str(version.id),
                    "version_number": version.version_number,
                },
            ),
        )
        session.flush()

    @staticmethod
    def _invalid_state(detail: str) -> ApiProblem:
        return ApiProblem(409, "INVALID_STATE_TRANSITION", "Invalid state transition", detail)
