from dataclasses import replace

import pytest
from app.auth.errors import ApiProblem
from app.export.repositories import CustomsRepository, RefundRepository
from app.export.schemas import CustomsCreate, FollowUpSchedule, RefundCreate
from app.export.services import ExportQueryService
from app.export.text_review import ExportTextReviewRequest, ExportTextReviewService
from app.platform.models import IdempotencyKey
from sqlalchemy import select
from test_export_acceptance_matrix import prepare_case, snapshot
from test_sales_foreign_commands import foreign_manager

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")


@pytest.mark.parametrize("refund", [False, True])
def test_export_remaining_tenant_entries(quotation_fixture, fake_storage, refund):
    f = quotation_fixture
    commands, owner, model, case_id = prepare_case(f, fake_storage, refund)
    foreign = foreign_manager(f)
    kind = "refund" if refund else "customs"
    path = "tax-refund-cases" if refund else "customs-declarations"
    headers = f.headers("quotation-other", f.organization_b)
    reviews = ExportTextReviewService(f.session_factory)
    preview = reviews.inspect(owner, kind, case_id)
    review_request = ExportTextReviewRequest(
        expected_version=preview.version,
        content_digest=preview.content_digest,
        release=True,
        confirmed=True,
        reason="Synthetic tenant review test",
    )
    follow_up = FollowUpSchedule(
        expected_version=preview.version, follow_up_date=None, reason="Synthetic follow up"
    )
    with f.session_factory() as session:
        row = session.get(model, case_id)
        request = (
            RefundCreate(customs_declaration_id=row.customs_declaration_id, expected_amount="10")
            if refund
            else CustomsCreate(
                shipment_id=row.shipment_id, declared_amount="100", currency_code="USD"
            )
        )

    def facts():
        with f.session_factory() as session:
            keys = list(
                session.execute(select(IdempotencyKey.__table__).order_by(IdempotencyKey.id))
                .mappings()
                .all()
            )
        return snapshot(f, model, case_id), keys

    before = facts()
    review_path = f"/api/v1/export-text/{kind}/{case_id}/review"
    responses = (
        f.client.get(f"/api/v1/{path}/{case_id}", headers=headers),
        f.client.get(f"/api/v1/{path}/{case_id}/activities", headers=headers),
        f.client.post(
            f"/api/v1/{path}",
            headers=headers | {"Idempotency-Key": "foreign-create"},
            json=request.model_dump(mode="json"),
        ),
        f.client.post(
            f"/api/v1/{path}/{case_id}/schedule-follow-up",
            headers=headers,
            json=follow_up.model_dump(mode="json"),
        ),
        f.client.get(review_path, headers=headers),
        f.client.post(
            review_path,
            headers=headers | {"Idempotency-Key": "foreign-review"},
            json=review_request.model_dump(mode="json"),
        ),
    )
    for response in responses:
        assert response.status_code == 404, response.text
    assert f.client.get(f"/api/v1/{path}", headers=headers).json() == {
        "items": [],
        "next_cursor": None,
        "has_more": False,
    }
    calls = (
        lambda: getattr(commands, f"create_{kind}")(foreign, request, key="direct-create"),
        lambda: commands.schedule_follow_up(foreign, case_id, follow_up, refund=refund),
        lambda: reviews.inspect(foreign, kind, case_id),
        lambda: reviews.decide(foreign, kind, case_id, review_request, key="direct-review"),
    )
    for call in calls:
        with pytest.raises(ApiProblem) as denied:
            call()
        assert denied.value.status == 404
    with f.session_factory() as session:
        query = ExportQueryService(session)
        with pytest.raises(ApiProblem) as denied:
            getattr(query, kind)(foreign, case_id)
        assert denied.value.status == 404
        with pytest.raises(ApiProblem) as denied:
            query.activities(foreign, case_id, refund=refund, cursor=None, limit=10)
        assert denied.value.status == 404
        assert getattr(query, f"{kind}_page")(foreign, cursor=None, limit=10) == ([], {}, False)
        repository = RefundRepository(session) if refund else CustomsRepository(session)
        for context, exists in ((owner, True), (foreign, False)):
            args = {"organization_id": context.organization_id, "record_id": case_id}
            assert (repository.get(**args) is not None) is exists
            assert (repository.locked(**args) is not None) is exists
            parent = (
                repository.by_declaration(
                    organization_id=context.organization_id,
                    declaration_id=request.customs_declaration_id,
                )
                if refund
                else repository.by_shipment(
                    organization_id=context.organization_id, shipment_id=request.shipment_id
                )
            )
            assert (parent is not None) is exists
        with pytest.raises(ApiProblem) as denied:
            getattr(query, kind)(replace(owner, permissions=frozenset()), case_id)
        assert denied.value.status == 403
    assert facts() == before
