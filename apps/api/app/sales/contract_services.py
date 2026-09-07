from collections.abc import Sequence
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.models import Company
from app.core.unit_of_work import UnitOfWork
from app.documents.evidence import require_contract_evidence
from app.finance.services import organization_today
from app.identity.models import Organization
from app.platform.idempotency import begin_command, complete_command
from app.platform.numbering import next_document_number
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.contract_models import ContractStatus, SalesContract
from app.sales.contract_schemas import (
    ContractCommand,
    ContractCreate,
    ContractItemSnapshot,
    ContractResponse,
    ContractSign,
    ContractSnapshot,
    ContractUpdate,
)
from app.sales.models import SalesOrder
from app.sales.order_enums import SalesOrderStatus
from app.sales.order_repositories import SalesOrderRepository
from app.sales.text_content import contract_response
from app.work.models import Activity


class ContractRepository:
    def __init__(self, session: Session):
        self.session = session

    def order(self, organization_id: UUID, order_id: UUID, *, lock: bool = False) -> SalesOrder:
        query = select(SalesOrder).where(
            SalesOrder.organization_id == organization_id,
            SalesOrder.id == order_id,
            SalesOrder.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self.session.scalar(query)
        if row is None:
            raise ApiProblem(
                404, "SALES_ORDER_NOT_FOUND", "Order not found", "The order was not found."
            )
        return row

    def get(
        self, organization_id: UUID, order_id: UUID, contract_id: UUID, *, lock: bool = False
    ) -> SalesContract:
        query = select(SalesContract).where(
            SalesContract.organization_id == organization_id,
            SalesContract.sales_order_id == order_id,
            SalesContract.id == contract_id,
            SalesContract.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self.session.scalar(query)
        if row is None:
            raise ApiProblem(
                404,
                "CONTRACT_NOT_FOUND",
                "Contract not found",
                "The contract was not found for this order.",
            )
        return row

    def list(
        self, organization_id: UUID, order_id: UUID, *, cursor: UUID | None, limit: int
    ) -> Sequence[SalesContract]:
        query = select(SalesContract).where(
            SalesContract.organization_id == organization_id,
            SalesContract.sales_order_id == order_id,
            SalesContract.deleted_at.is_(None),
        )
        if cursor:
            anchor = self.get(organization_id, order_id, cursor)
            query = query.where(
                tuple_(SalesContract.created_at, SalesContract.id) < (anchor.created_at, anchor.id)
            )
        return self.session.scalars(
            query.order_by(SalesContract.created_at.desc(), SalesContract.id.desc()).limit(
                limit + 1
            )
        ).all()


class ContractQuery:
    def __init__(self, session: Session):
        self.repository = ContractRepository(session)

    def list(
        self, context: RequestContext, order_id: UUID, *, cursor: UUID | None, limit: int
    ) -> Sequence[ContractResponse]:
        context.require(Permission.CONTRACT_READ)
        self.repository.order(context.organization_id, order_id)
        return [
            contract_response(context, row)
            for row in self.repository.list(
                context.organization_id, order_id, cursor=cursor, limit=limit
            )
        ]

    def get(self, context: RequestContext, order_id: UUID, contract_id: UUID) -> ContractResponse:
        context.require(Permission.CONTRACT_READ)
        self.repository.order(context.organization_id, order_id)
        return contract_response(
            context, self.repository.get(context.organization_id, order_id, contract_id)
        )


class ContractService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        *,
        audit_recorder: AuditRecorder | None = None,
        outbox_recorder: OutboxRecorder | None = None,
    ):
        self.factory = factory
        self.audit = audit_recorder or AuditRecorder()
        self.outbox = outbox_recorder or OutboxRecorder()

    def execute(
        self,
        context: RequestContext,
        order_id: UUID,
        *,
        action: str,
        data: dict[str, object],
        key: str,
        contract_id: UUID | None = None,
    ) -> ContractResponse:
        schemas: dict[str, type[BaseModel]] = {
            "created": ContractCreate,
            "updated": ContractUpdate,
            "signed": ContractSign,
            "voided": ContractCommand,
        }
        if action not in schemas:
            raise ValueError("Unsupported contract command")
        context.require(
            Permission.CONTRACT_SIGN if action == "signed" else Permission.CONTRACT_WRITE
        )
        request = schemas[action].model_validate(data)
        with UnitOfWork(self.factory) as uow:
            session = uow.session
            command = begin_command(
                session,
                context,
                scope=f"sales_contract.{action}",
                key=key,
                payload={
                    "order_id": str(order_id),
                    "contract_id": str(contract_id) if contract_id else None,
                    **request.model_dump(),
                },
            )
            repository = ContractRepository(session)
            order = repository.order(context.organization_id, order_id, lock=True)
            if command.resource_id:
                row = repository.get(context.organization_id, order_id, command.resource_id)
                uow.commit()
                return contract_response(context, row)
            if order.status in {SalesOrderStatus.CANCELLED, SalesOrderStatus.COMPLETED}:
                raise ApiProblem(
                    409,
                    "CONTRACT_ORDER_FINALIZED",
                    "Order finalized",
                    "Finalized orders cannot change contract records.",
                )
            before = None
            reason = None
            if action == "created":
                assert isinstance(request, ContractCreate)
                active = session.scalar(
                    select(SalesContract.id).where(
                        SalesContract.organization_id == context.organization_id,
                        SalesContract.sales_order_id == order_id,
                        SalesContract.status != ContractStatus.VOIDED,
                        SalesContract.deleted_at.is_(None),
                    )
                )
                if active:
                    raise ApiProblem(
                        409,
                        "CONTRACT_ALREADY_EXISTS",
                        "Contract exists",
                        "Use the existing non-voided contract for this order.",
                    )
                row = SalesContract(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    sales_order_id=order_id,
                    contract_number=next_document_number(session, context, "SALES_CONTRACT", "SC"),
                    status=ContractStatus.DRAFT,
                    currency_code=order.currency_code,
                    total=order.total,
                    commercial_snapshot=self._snapshot(session, context, order),
                    external_reference=request.external_reference,
                    notes=request.notes,
                )
                session.add(row)
                session.flush()
            else:
                assert contract_id is not None and isinstance(request, ContractCommand)
                row = repository.get(context.organization_id, order_id, contract_id, lock=True)
                if row.version != request.expected_version:
                    raise ApiProblem(
                        409,
                        "VERSION_CONFLICT",
                        "Version conflict",
                        "Refresh and review the contract before submitting.",
                    )
                if row.status != ContractStatus.DRAFT:
                    raise ApiProblem(
                        409,
                        "CONTRACT_IMMUTABLE",
                        "Contract immutable",
                        "Only draft contracts can change.",
                    )
                before = ContractResponse.model_validate(row).model_dump(mode="json")
                reason = request.reason
                if isinstance(request, ContractSign):
                    if order.status == SalesOrderStatus.DRAFT:
                        raise ApiProblem(
                            409,
                            "ORDER_NOT_CONFIRMED",
                            "Order not confirmed",
                            "Confirm the order before recording contract signature.",
                        )
                    if request.signed_on > organization_today(session, context.organization_id):
                        raise ApiProblem(
                            422,
                            "CONTRACT_SIGNATURE_IN_FUTURE",
                            "Future signature",
                            "Record an already occurred signature date.",
                        )
                    require_contract_evidence(
                        session, context, order_id, request.document_version_id
                    )
                    row.status = ContractStatus.SIGNED
                    row.signed_on = request.signed_on
                    row.signed_document_version_id = request.document_version_id
                elif isinstance(request, ContractUpdate):
                    if "external_reference" in request.model_fields_set:
                        row.external_reference = request.external_reference
                    if "notes" in request.model_fields_set:
                        row.notes = request.notes
                else:
                    row.status = ContractStatus.VOIDED
                row.updated_by = context.user_id
            session.flush()
            after = ContractResponse.model_validate(row).model_dump(mode="json")
            session.add(
                Activity(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    subject_type="sales_order",
                    subject_id=order_id,
                    activity_type=f"sales_contract.{action}",
                    summary=f"{row.contract_number}: {action}",
                    details={"contract_id": str(row.id)},
                    correlation_id=context.request_id,
                )
            )
            self.audit.record(
                session,
                context,
                action=f"sales_contract.{action}",
                target_type="sales_contract",
                target_id=row.id,
                before=before,
                after=after,
                reason=reason,
            )
            self.outbox.record(
                session,
                context,
                DomainEvent(
                    f"sales_contract.{action}.v1",
                    "sales_contract",
                    row.id,
                    {"contract_id": str(row.id), "sales_order_id": str(order_id)},
                ),
            )
            complete_command(command, row.id, "sales_contract")
            uow.commit()
            return contract_response(context, row)

    @staticmethod
    def _snapshot(
        session: Session, context: RequestContext, order: SalesOrder
    ) -> dict[str, object]:
        seller = session.scalar(
            select(Organization.name).where(Organization.id == context.organization_id)
        )
        customer = session.scalar(
            select(Company.name).where(
                Company.organization_id == context.organization_id,
                Company.id == order.company_id,
                Company.deleted_at.is_(None),
            )
        )
        if seller is None or customer is None:
            raise ApiProblem(
                404,
                "CONTRACT_PARTY_NOT_FOUND",
                "Party not found",
                "Contract parties must exist in this organization.",
            )
        items = SalesOrderRepository(session).items(
            organization_id=context.organization_id, sales_order_id=order.id
        )
        return ContractSnapshot(
            order_number=order.order_number,
            quotation_version_id=order.quotation_version_id,
            seller_name=seller,
            customer_name=customer,
            payment_terms=order.payment_terms,
            delivery_terms=order.delivery_terms,
            deposit_amount=order.deposit_amount,
            deposit_due_date=order.deposit_due_date,
            items=[
                ContractItemSnapshot(
                    line_number=item.line_number,
                    sku=item.sku_snapshot,
                    description=item.description_snapshot,
                    unit=item.unit_snapshot,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    tax_amount=item.tax_amount,
                    freight_amount=item.freight_amount,
                    line_total=item.line_total,
                )
                for item in items
            ],
        ).model_dump(mode="json")
