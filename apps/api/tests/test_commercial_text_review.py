from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.catalog.models import Product
from app.catalog.repositories import ProductRepository
from app.catalog.services import ProductQueryService
from app.catalog.text_review import ProductTextReviewRequest, ProductTextReviewService
from app.identity.enums import MembershipRole
from app.inquiries.models import Inquiry
from app.inquiries.repositories import InquiryRepository
from app.inquiries.services import InquiryQueryService
from app.inquiries.text_review import InquiryTextReviewRequest, InquiryTextReviewService
from app.platform.models import AuditLog, OutboxEvent
from app.sales.contract_models import SalesContract
from app.sales.contract_services import ContractQuery
from app.sales.models import QuotationItem, QuotationVersion, SalesOrder, SalesOrderItem
from app.sales.order_repositories import SalesOrderRepository
from app.sales.order_services import SalesOrderQueryService
from app.sales.repositories import QuotationRepository
from app.sales.services import QuotationQueryService
from app.sales.text_review import CommercialTextReviewRequest, CommercialTextReviewService
from app.work.models import Activity
from legacy_migration import verify_legacy_guard, verify_legacy_upgrade
from sqlalchemy import event
from test_document_review import counts, reviewer
from test_order_procurement_vertical_slice import create_confirmed_order
from test_quotation_vertical_slice import state_request
from test_sales_contracts import create as create_contract

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)
MODELS = {
    "product": Product,
    "inquiry": Inquiry,
    "quotation_version": QuotationVersion,
    "sales_order": SalesOrder,
    "sales_contract": SalesContract,
}
PERMISSIONS = {
    "product": Permission.PRODUCT_READ,
    "inquiry": Permission.INQUIRY_READ,
    "quotation_version": Permission.QUOTATION_READ,
    "sales_order": Permission.ORDER_READ,
    "sales_contract": Permission.CONTRACT_READ,
}
SECRET = "CONFIDENTIAL-SOURCE-350"


def seed(f):
    order, _, _ = create_confirmed_order(f)
    contract = create_contract(f, order)
    with f.session_factory.begin() as session:
        version = session.get(QuotationVersion, UUID(order["quotation_version_id"]))
        from app.sales.models import Quotation

        quote = session.get(Quotation, version.quotation_id)
        ids = {
            "product": UUID(order["items"][0]["product_id"]),
            "inquiry": quote.inquiry_id,
            "quotation_version": version.id,
            "sales_order": UUID(order["id"]),
            "sales_contract": UUID(contract["id"]),
        }
        for kind, model in MODELS.items():
            row = session.get(model, ids[kind])
            if kind in {"product", "inquiry"}:
                row.description = SECRET
            elif kind == "sales_contract":
                row.notes = SECRET
                row.commercial_snapshot = {**row.commercial_snapshot, "payment_terms": SECRET}
            else:
                row.payment_terms = SECRET
                row.delivery_terms = SECRET
    return ids, UUID(order["quotation_id"])


def review(f, kind):
    if kind == "product":
        service, schema = ProductTextReviewService(f.session_factory), ProductTextReviewRequest
    elif kind == "inquiry":
        service, schema = InquiryTextReviewService(f.session_factory), InquiryTextReviewRequest
    else:
        service = CommercialTextReviewService(f.session_factory)
        return (
            lambda c, r: service.inspect(c, kind, r),
            lambda c, r, q, key: service.decide(c, kind, r, q, key=key),
            CommercialTextReviewRequest,
        )
    return service.inspect, lambda c, r, q, key: service.decide(c, r, q, key=key), schema


def request(schema, snapshot, release=True):
    return schema(
        expected_version=snapshot.version,
        content_digest=snapshot.content_digest,
        release=release,
        confirmed=True,
        reason="Reviewed complete source fixture",
    )


def route(kind, record_id):
    if kind in {"product", "inquiry"}:
        resource = "products" if kind == "product" else "inquiries"
        return f"/api/v1/{resource}/{record_id}/text-review"
    return f"/api/v1/commercial-text/{kind}/{record_id}/review"


def read(f, context, kind, ids, quote_id):
    with f.session_factory() as session:
        if kind == "product":
            service = ProductQueryService(ProductRepository(session))
            result = service.get(context, ids[kind])
            assert result in service.list(context, query=None, limit=50)
        elif kind == "inquiry":
            service = InquiryQueryService(InquiryRepository(session))
            result = service.get(context, ids[kind])
            assert result in service.list(context, status=None, limit=50)
        elif kind == "quotation_version":
            result = (
                QuotationQueryService(QuotationRepository(session))
                .get(context, quote_id)
                .current_version
            )
        elif kind == "sales_order":
            service = SalesOrderQueryService(SalesOrderRepository(session))
            result = service.get(context, ids[kind])
            assert result in service.list(context, limit=50)
        else:
            service = ContractQuery(session)
            result = service.get(context, ids["sales_order"], ids[kind])
            assert result in service.list(context, ids["sales_order"], cursor=None, limit=50)
        assert not session.dirty
        return result


@pytest.mark.parametrize("kind", list(MODELS))
@pytest.mark.parametrize("role", list(MembershipRole))
def test_commercial_roles_source_service_http_release_revoke(quotation_fixture, kind, role):
    f = quotation_fixture
    ids, quote_id = seed(f)
    subject, context = reviewer(f, role)
    inspect, decide, schema = review(f, kind)
    endpoint = route(kind, ids[kind])
    headers = f.headers(subject, f.organization_a)
    privileged = Permission.PROFIT_READ in context.permissions
    if PERMISSIONS[kind] not in context.permissions:
        with pytest.raises(ApiProblem) as denied:
            read(f, context, kind, ids, quote_id)
        assert denied.value.status == 403
        assert f.client.get(endpoint, headers=headers).status_code == 403
        return
    result = read(f, context, kind, ids, quote_id)
    assert result.content_visible is privileged
    assert (SECRET in result.model_dump_json()) is privileged
    if not privileged:
        assert f.client.get(endpoint, headers=headers).status_code == 403
        with pytest.raises(ApiProblem) as denied:
            inspect(context, ids[kind])
        assert denied.value.status == 403
        return
    original = inspect(context, ids[kind])
    before = counts(f)
    command = request(schema, original)
    response = f.client.post(
        endpoint, headers=headers | {"Idempotency-Key": "release"}, json=command.model_dump()
    )
    assert response.status_code == 200, response.text
    opened = inspect(context, ids[kind])
    assert opened.version == original.version + 1 and opened.released
    low = replace(context, permissions=context.permissions - {Permission.PROFIT_READ})
    assert SECRET in read(f, low, kind, ids, quote_id).model_dump_json()
    decide(context, ids[kind], request(schema, opened, False), "revoke")
    assert not decide(context, ids[kind], command, "release").released
    restricted = read(f, low, kind, ids, quote_id)
    assert SECRET not in restricted.model_dump_json()
    if kind == "product":
        assert restricted.sku == result.sku and restricted.name == result.name
        assert restricted.standard_cost is None
    elif kind == "inquiry":
        assert restricted.customer_reference == "RFQ-88"
    else:
        assert restricted.total == result.total
    assert counts(f) == [value + 2 for value in before]
    with pytest.raises(ApiProblem) as foreign:
        inspect(replace(context, organization_id=f.organization_b), ids[kind])
    assert foreign.value.status == 404
    with pytest.raises(ApiProblem) as missing_read:
        inspect(replace(context, permissions=frozenset({Permission.PROFIT_READ})), ids[kind])
    assert missing_read.value.status == 403


@pytest.mark.parametrize("kind", list(MODELS))
@pytest.mark.parametrize("stage", [Activity, AuditLog, OutboxEvent])
def test_commercial_review_atomic_evidence(quotation_fixture, kind, stage):
    f = quotation_fixture
    ids, _ = seed(f)
    _, context = reviewer(f)
    inspect, decide, schema = review(f, kind)
    before = counts(f)
    original = inspect(context, ids[kind])

    def fail(*args):
        raise RuntimeError("injected review failure")

    event.listen(stage, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            decide(context, ids[kind], request(schema, original), "failed")
    finally:
        event.remove(stage, "before_insert", fail)
    assert inspect(context, ids[kind]) == original and counts(f) == before


@pytest.mark.parametrize("kind", list(MODELS))
def test_commercial_review_race_stale_restored_and_deleted_owner(quotation_fixture, kind):
    f = quotation_fixture
    ids, _ = seed(f)
    _, context = reviewer(f)
    inspect, decide, schema = review(f, kind)
    original = inspect(context, ids[kind])
    barrier = Barrier(2)

    def race(release):
        barrier.wait(timeout=10)
        try:
            return decide(context, ids[kind], request(schema, original, release), f"race-{release}")
        except ApiProblem as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, (True, False)))
    errors = [row for row in results if isinstance(row, ApiProblem)]
    assert len(errors) == 1 and errors[0].code == "VERSION_CONFLICT"
    open_request = request(schema, inspect(context, ids[kind]))
    opened = decide(context, ids[kind], open_request, "open")
    field = (
        "description"
        if kind in {"product", "inquiry"}
        else "notes"
        if kind == "sales_contract"
        else "payment_terms"
    )
    for value in ("Changed", SECRET):
        with f.session_factory.begin() as session:
            setattr(session.get(MODELS[kind], ids[kind]), field, value)
    assert not inspect(context, ids[kind]).released
    with pytest.raises(ApiProblem) as stale:
        decide(context, ids[kind], request(schema, opened), "stale")
    assert stale.value.code == "VERSION_CONFLICT"
    with f.session_factory.begin() as session:
        session.get(MODELS[kind], ids[kind]).deleted_at = datetime.now(UTC)
    with pytest.raises(ApiProblem) as deleted:
        decide(context, ids[kind], open_request, "open")
    assert deleted.value.status == 404


def test_commercial_legacy_facts_are_preserved_and_downgrade_refused(quotation_fixture):
    f = quotation_fixture
    ids, _ = seed(f)

    def check(engine):
        from sqlalchemy.orm import Session

        with Session(engine) as session:
            for kind, model in MODELS.items():
                row = session.get(model, ids[kind])
                assert row.released_digest is row.reviewed_by is row.reviewed_at is None

    verify_legacy_upgrade(f.engine, "20260906_0028", check=check)
    verify_legacy_guard(f.engine, "20260906_0029", "20260906_0028", "Commercial evidence exists")


@pytest.mark.parametrize(
    "kind,model", [("quotation_version", QuotationItem), ("sales_order", SalesOrderItem)]
)
def test_item_mutation_and_restoration_invalidates_parent_release(quotation_fixture, kind, model):
    from sqlalchemy import select

    f = quotation_fixture
    ids, quote_id = seed(f)
    _, context = reviewer(f)
    inspect, decide, schema = review(f, kind)
    before = inspect(context, ids[kind])
    decide(context, ids[kind], request(schema, before), "open")
    with f.session_factory() as session:
        item = session.scalars(select(model)).first()
        item_id, text = item.id, item.description_snapshot
    for value in ("Changed item", text):
        with f.session_factory.begin() as session:
            session.get(model, item_id).description_snapshot = value
    assert not inspect(context, ids[kind]).released
    low = replace(context, permissions=context.permissions - {Permission.PROFIT_READ})
    assert not read(f, low, kind, ids, quote_id).content_visible


def test_copy_chain_preserves_original_text_without_inheriting_disclosure(quotation_fixture):
    from app.sales.contract_services import ContractService
    from app.sales.order_services import SalesOrderCommandService
    from app.sales.services import QuotationCommandService
    from sqlalchemy import select
    from test_quotation_vertical_slice import create_commercial_inputs

    f = quotation_fixture
    inputs, _, _ = create_commercial_inputs(f)
    _, high = reviewer(f)
    low = replace(high, permissions=frozenset(Permission) - {Permission.PROFIT_READ})
    product_id = UUID(inputs["items"][0]["product_id"])
    inquiry_id = UUID(inputs["inquiry_id"])
    for kind, record_id in (("product", product_id), ("inquiry", inquiry_id)):
        inspect, decide, schema = review(f, kind)
        decide(high, record_id, request(schema, inspect(high, record_id)), f"release-{kind}")
    quotes = QuotationCommandService(f.session_factory)
    quote = quotes.create(high, inputs)
    with f.session_factory() as session:
        hidden = QuotationQueryService(QuotationRepository(session)).get(low, quote.id)
        assert not hidden.current_version.content_visible
        assert all(item.description_snapshot is None for item in hidden.current_version.items)
    review_service = CommercialTextReviewService(f.session_factory)
    preview = review_service.inspect(high, "quotation_version", quote.current_version.id)
    review_service.decide(
        high,
        "quotation_version",
        preview.record_id,
        request(CommercialTextReviewRequest, preview),
        key="quote-open",
    )
    revision_request = {
        "expected_version_id": quote.current_version.id,
        "items": [
            {
                "source_item_id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
            }
            for item in quote.current_version.items
        ],
    }
    revised = quotes.revise(low, quote.id, revision_request, key="revision")
    assert not revised.content_visible and revised.payment_terms is None
    assert quotes.revise(low, quote.id, revision_request, key="revision").items == revised.items
    quotes.submit(low, quote.id, state_request(f, str(quote.id)), key="copy-submit")
    quotes.approve(high, quote.id, state_request(f, str(quote.id)), key="copy-approve")
    quotes.send(low, quote.id, state_request(f, str(quote.id)), key="copy-send")
    acceptance = state_request(f, str(quote.id))
    accepted = quotes.accept(low, quote.id, acceptance, key="copy-accept")
    assert not accepted.content_visible
    assert not quotes.accept(low, quote.id, acceptance, key="copy-accept").content_visible
    orders = SalesOrderCommandService(f.session_factory)
    order_request = {"quotation_id": quote.id, "deposit_rate": "0"}
    order = orders.create(low, order_request)
    assert not order.content_visible and order.items[0].description_snapshot is None
    assert not orders.create(low, order_request).content_visible
    preview = review_service.inspect(high, "sales_order", order.id)
    review_service.decide(
        high,
        "sales_order",
        order.id,
        request(CommercialTextReviewRequest, preview),
        key="order-open",
    )
    contracts = ContractService(f.session_factory)
    body = {"notes": SECRET, "external_reference": "CUSTOMER-CONTRACT-ID"}
    contract = contracts.execute(low, order.id, action="created", data=body, key="contract")
    assert contract.notes is None and not contract.content_visible
    assert contract.commercial_snapshot.items[0].description is None
    assert not contracts.execute(
        low, order.id, action="created", data=body, key="contract"
    ).content_visible
    updated = contracts.execute(
        low,
        order.id,
        action="updated",
        contract_id=contract.id,
        data={
            "expected_version": contract.version,
            "external_reference": "NEW-ID",
            "reason": "Identifier only",
        },
        key="update-id",
    )
    assert updated.notes is None and updated.external_reference == "NEW-ID"
    with f.session_factory() as session:
        original = quote.current_version.items[0].description_snapshot
        row = session.get(SalesContract, contract.id)
        assert row.notes == SECRET
        assert row.commercial_snapshot["items"][0]["description"] == original
        assert (
            session.scalars(
                select(SalesOrderItem)
                .where(SalesOrderItem.sales_order_id == order.id)
                .order_by(SalesOrderItem.line_number)
            )
            .first()
            .description_snapshot
            == original
        )
        assert (
            session.scalars(
                select(QuotationItem)
                .where(QuotationItem.quotation_version_id == revised.id)
                .order_by(QuotationItem.line_number)
            )
            .first()
            .description_snapshot
            == original
        )
