from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.export.enums import CustomsStatus, TaxRefundStatus
from app.export.models import CustomsDeclaration, TaxRefundCase
from app.export.schemas import (
    CaseCommand,
    CaseReject,
    CustomsClear,
    CustomsCreate,
    FollowUpSchedule,
    ManualSubmission,
    RefundCreate,
    RefundReceived,
)
from app.export.services import ExportCommandService
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_shipment_documents_vertical_slice import (
    create_shipment,
    executing_order,
    upload_required_document,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")

# Independent ADR009 expectations; never import the implementation transition maps.
CUSTOMS = {
    "prepare": ("DRAFT", "DOCUMENTS_PENDING"),
    "ready": ("DOCUMENTS_PENDING", "READY"),
    "submit": ("READY", "SUBMITTED"),
    "clear": ("SUBMITTED", "CLEARED"),
    "reject": ("SUBMITTED", "REJECTED"),
}
REFUND = {
    "prepare": ("NOT_READY", "DOCUMENTS_PENDING"),
    "ready": ("DOCUMENTS_PENDING", "READY"),
    "submit": ("READY", "SUBMITTED"),
    "process": ("SUBMITTED", "PROCESSING"),
    "receive": ("PROCESSING", "REFUNDED"),
    "reject": ("PROCESSING", "REJECTED"),
}


def prepare_case(f, storage, refund):
    order = executing_order(f)
    shipment = create_shipment(
        f,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    )
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    service = ExportCommandService(f.session_factory)
    declaration, _ = service.create_customs(
        context,
        CustomsCreate(
            shipment_id=UUID(shipment["id"]),
            declared_amount=Decimal("100"),
            currency_code="USD",
            required_document_types=["COMMERCIAL_INVOICE"],
        ),
        key="matrix-customs",
    )
    case_id = declaration.id
    model = CustomsDeclaration
    if refund:
        # Disposable state preparation isolates the refund transition under test.
        # The separate vertical test proves the normal clearance command chain.
        with f.session_factory.begin() as session:
            session.get(CustomsDeclaration, declaration.id).status = "CLEARED"
        case, _ = service.create_refund(
            context,
            RefundCreate(
                customs_declaration_id=declaration.id,
                expected_amount=Decimal("10"),
                required_document_types=["COMMERCIAL_INVOICE"],
            ),
            key="matrix-refund",
        )
        case_id = case.id
        model = TaxRefundCase
    upload_required_document(
        f,
        storage,
        shipment_id=str(case_id),
        document_type="COMMERCIAL_INVOICE",
        target_type="TAX_REFUND_CASE" if refund else "CUSTOMS_DECLARATION",
    )
    return service, context, model, case_id


def reset_case(f, model, case_id, state):
    with f.session_factory.begin() as session:
        case = session.get(model, case_id)
        case.status = state
        case.submitted_on = date(2026, 9, 1)
        case.external_reference = "MATRIX-ORIGINAL"
        case.rejection_reason = None
        case.follow_up_date = None
        if model is CustomsDeclaration:
            case.cleared_on = None
        else:
            case.refunded_on = None
            case.refunded_amount = Decimal("0")


def snapshot(f, model, case_id):
    with f.session_factory() as session:
        row = dict(
            session.execute(select(model.__table__).where(model.id == case_id)).mappings().one()
        )
        counts = tuple(
            session.scalar(select(func.count()).select_from(table))
            for table in (CustomsDeclaration, TaxRefundCase, Activity, AuditLog, OutboxEvent)
        )
        return row, counts


def command_request(command, version):
    fields = {"expected_version": version, "reason": "Synthetic matrix evidence"}
    if command == "submit":
        return ManualSubmission(
            **fields, external_reference="MATRIX-SUBMITTED", occurred_on=date(2026, 9, 2)
        )
    if command == "clear":
        return CustomsClear(**fields, occurred_on=date(2026, 9, 3))
    if command == "receive":
        return RefundReceived(**fields, occurred_on=date(2026, 9, 3), refunded_amount=Decimal("8"))
    if command == "reject":
        return CaseReject(**fields)
    return CaseCommand(**fields)


@pytest.mark.parametrize(
    ("refund", "state"),
    [(False, state) for state in CustomsStatus] + [(True, state) for state in TaxRefundStatus],
)
def test_every_export_state_command_pair(quotation_fixture, fake_storage, refund, state):
    f = quotation_fixture
    service, context, model, case_id = prepare_case(f, fake_storage, refund)
    transition = service.refund_command if refund else service.customs_command
    for command, (source, target) in (REFUND if refund else CUSTOMS).items():
        reset_case(f, model, case_id, state)
        before, counts = snapshot(f, model, case_id)
        request = command_request(command, before["version"])
        if state != source:
            with pytest.raises(ApiProblem) as error:
                transition(context, case_id, command, request)
            assert error.value.code == "INVALID_STATE_TRANSITION"
            assert snapshot(f, model, case_id) == (before, counts)
        else:
            response, missing = transition(context, case_id, command, request)
            after, after_counts = snapshot(f, model, case_id)
            assert response.status == after["status"] == target
            assert missing == []
            assert after["version"] == before["version"] + 1
            assert after["updated_by"] == context.user_id
            assert after_counts == (*counts[:2], *(value + 1 for value in counts[2:]))
            if command == "submit":
                assert after["external_reference"] == "MATRIX-SUBMITTED"
                assert after["submitted_on"] == date(2026, 9, 2)
            elif command == "clear":
                assert after["cleared_on"] == date(2026, 9, 3)
            elif command == "receive":
                assert after["refunded_on"] == date(2026, 9, 3)
                assert after["refunded_amount"] == Decimal("8")
                assert after["expected_amount"] == Decimal("10")
            elif command == "reject":
                assert after["rejection_reason"] == request.reason


@pytest.mark.parametrize("refund", [False, True])
@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_each_export_command_rolls_back_on_each_evidence_failure(
    quotation_fixture, fake_storage, refund, table
):
    f = quotation_fixture
    service, context, model, case_id = prepare_case(f, fake_storage, refund)
    transition = service.refund_command if refund else service.customs_command
    transitions = REFUND if refund else CUSTOMS
    for command in (*transitions, "follow_up"):
        source = transitions[command][0] if command != "follow_up" else "DOCUMENTS_PENDING"
        reset_case(f, model, case_id, source)
        before, counts = snapshot(f, model, case_id)

        def fail(conn, cursor, statement, parameters, execution_context, executemany):
            if statement.startswith(f"INSERT INTO {table}"):
                raise RuntimeError("Injected export evidence failure")

        event.listen(f.engine, "before_cursor_execute", fail)
        try:
            with pytest.raises(RuntimeError, match="Injected export evidence failure"):
                if command == "follow_up":
                    service.schedule_follow_up(
                        context,
                        case_id,
                        FollowUpSchedule(
                            expected_version=before["version"],
                            follow_up_date=date(2026, 9, 9),
                            reason="Synthetic follow-up",
                        ),
                        refund=refund,
                    )
                else:
                    transition(
                        context, case_id, command, command_request(command, before["version"])
                    )
        finally:
            event.remove(f.engine, "before_cursor_execute", fail)
        assert snapshot(f, model, case_id) == (before, counts)


@pytest.mark.parametrize("refund", [False, True])
@pytest.mark.parametrize("role", list(MembershipRole))
def test_every_export_transition_http_and_service_permissions(
    quotation_fixture, fake_storage, refund, role
):
    f = quotation_fixture
    service, context, model, case_id = prepare_case(f, fake_storage, refund)
    with f.session_factory.begin() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_a,
                OrganizationMembership.user_id == f.sales_user,
            )
        )
        membership.role = role
    role_context = RequestContext(
        user_id=context.user_id,
        organization_id=context.organization_id,
        permissions=permissions_for_role(role),
        request_id=uuid4(),
    )
    allowed = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.OPERATIONS}
    path = "tax-refund-cases" if refund else "customs-declarations"
    transition = service.refund_command if refund else service.customs_command
    for command, (source, target) in (REFUND if refund else CUSTOMS).items():
        reset_case(f, model, case_id, source)
        before, counts = snapshot(f, model, case_id)
        request = command_request(command, before["version"])
        response = f.client.post(
            f"/api/v1/{path}/{case_id}/{command}",
            headers=f.headers("quotation-sales", f.organization_a),
            json=request.model_dump(mode="json"),
        )
        assert response.status_code == (200 if allowed else 403), response.text
        if allowed:
            after, after_counts = snapshot(f, model, case_id)
            assert after["status"] == response.json()["status"] == target
            assert after["updated_by"] == f.sales_user
            assert after["version"] == before["version"] + 1
            assert after_counts == (*counts[:2], *(value + 1 for value in counts[2:]))
        else:
            assert response.json()["code"] == "PERMISSION_DENIED"
            with pytest.raises(ApiProblem) as error:
                transition(role_context, case_id, command, request)
            assert error.value.code == "PERMISSION_DENIED"
            assert snapshot(f, model, case_id) == (before, counts)


@pytest.mark.parametrize("refund", [False, True])
def test_all_export_transitions_reject_foreign_id_and_stale_version(
    quotation_fixture, fake_storage, refund
):
    f = quotation_fixture
    _, _, model, case_id = prepare_case(f, fake_storage, refund)
    with f.session_factory.begin() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_b
            )
        )
        membership.role = MembershipRole.OPERATIONS
    path = "tax-refund-cases" if refund else "customs-declarations"
    for command, (source, _) in (REFUND if refund else CUSTOMS).items():
        reset_case(f, model, case_id, source)
        before, counts = snapshot(f, model, case_id)
        for subject, organization, version, status, code in (
            ("quotation-other", f.organization_b, before["version"], 404, "EXPORT_CASE_NOT_FOUND"),
            (
                "quotation-operations",
                f.organization_a,
                before["version"] + 1,
                409,
                "VERSION_CONFLICT",
            ),
        ):
            response = f.client.post(
                f"/api/v1/{path}/{case_id}/{command}",
                headers=f.headers(subject, organization),
                json=command_request(command, version).model_dump(mode="json"),
            )
            assert response.status_code == status, response.text
            assert response.json()["code"] == code
            assert snapshot(f, model, case_id) == (before, counts)


@pytest.mark.parametrize("refund", [False, True])
def test_follow_up_can_be_set_and_cleared_only_in_nonterminal_states(
    quotation_fixture, fake_storage, refund
):
    f = quotation_fixture
    service, context, model, case_id = prepare_case(f, fake_storage, refund)
    states = TaxRefundStatus if refund else CustomsStatus
    terminal = {"REFUNDED", "REJECTED"} if refund else {"CLEARED", "REJECTED"}
    for state in states:
        reset_case(f, model, case_id, state)
        for due in (date(2026, 9, 9), None):
            before, counts = snapshot(f, model, case_id)
            request = FollowUpSchedule(
                expected_version=before["version"],
                follow_up_date=due,
                reason="Synthetic reminder update",
            )
            if state in terminal:
                with pytest.raises(ApiProblem) as error:
                    service.schedule_follow_up(context, case_id, request, refund=refund)
                assert error.value.code == "EXPORT_CASE_FINALIZED"
                assert snapshot(f, model, case_id) == (before, counts)
            else:
                response, _ = service.schedule_follow_up(context, case_id, request, refund=refund)
                after, after_counts = snapshot(f, model, case_id)
                assert after["status"] == state
                assert after["follow_up_date"] == response.follow_up_date == due
                assert after["version"] == before["version"] + 1
                assert after_counts == (*counts[:2], *(value + 1 for value in counts[2:]))
