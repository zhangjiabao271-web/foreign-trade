from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.archive import CompanyArchiveService
from app.companies.models import Company, Contact
from app.platform.records import AuditRecorder, OutboxRecorder
from app.work.models import Activity
from legacy_migration import verify_legacy_upgrade
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_migrations import alembic_config
from test_quotation_vertical_slice import create_opportunity, table_counts

pytest_plugins = ("test_quotation_vertical_slice",)


def headers(f, key="create-company", subject="quotation-sales", organization=None):
    return f.headers(subject, organization or f.organization_a) | {"Idempotency-Key": key}


def create(f):
    response = f.client.post(
        "/api/v1/companies",
        headers=headers(f),
        json={
            "name": "Northern Components",
            "country_code": "DE",
            "roles": ["CUSTOMER", "SUPPLIER"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_edit_contact_and_role_unification(quotation_fixture):
    f = quotation_fixture
    row = create(f)
    assert row["roles"] == ["CUSTOMER", "SUPPLIER"]
    before = table_counts(f)
    assert create(f) == row
    assert table_counts(f) == before
    duplicate = f.client.post(
        "/api/v1/companies",
        headers=headers(f, "duplicate"),
        json={"name": "  NORTHERN   components  ", "roles": ["AGENT"]},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "COMPANY_NAME_EXISTS"
    path = f"/api/v1/companies/{row['id']}"
    request = {
        "name": "Northern Components Trading",
        "country_code": "DE",
        "website": "https://example.test",
        "expected_version": row["version"],
        "reason": "Verified company name",
    }
    edited = f.client.put(path, headers=headers(f, "edit"), json=request)
    assert edited.status_code == 200, edited.text
    assert edited.json()["roles"] == row["roles"]
    assert f.client.put(path, headers=headers(f, "edit"), json=request).json() == edited.json()
    assert f.client.put(path, headers=headers(f, "stale"), json=request).status_code == 409
    contact = f.client.post(
        path + "/contacts",
        headers=headers(f, "contact"),
        json={
            "full_name": "Marta",
            "email": "Marta@Example.Test",
            "phone": "+49 123",
            "job_title": "Buyer",
        },
    )
    assert contact.status_code == 201, contact.text
    contact = contact.json()
    with f.session_factory() as session:
        assert session.get(Contact, UUID(contact["id"])).email_normalized == "marta@example.test"
    contact_path = path + f"/contacts/{contact['id']}"
    update = {
        "full_name": "Marta Klein",
        "email": "marta@example.test",
        "expected_version": contact["version"],
        "reason": "Confirmed name",
    }
    edited_contact = f.client.put(contact_path, headers=headers(f, "edit-contact"), json=update)
    assert edited_contact.status_code == 200, edited_contact.text
    assert edited_contact.json()["company_id"] == row["id"]
    assert f.client.get(path + "/contacts", headers=headers(f)).json()["items"] == [
        edited_contact.json()
    ]
    assert f.client.get(
        "/api/v1/companies?query=NORTHERN&role=SUPPLIER", headers=headers(f)
    ).json()["items"] == [edited.json()]
    assert f.client.get("/api/v1/companies?query=%25", headers=headers(f)).json()["items"] == []
    assert f.client.get(path + "/activities?limit=1", headers=headers(f)).json()["has_more"]


def test_archive_tenant_authorization_and_contact_parent_checks(quotation_fixture):
    f = quotation_fixture
    row = create(f)
    path = f"/api/v1/companies/{row['id']}"
    foreign = headers(f, subject="quotation-other", organization=f.organization_b)
    before = table_counts(f)
    for suffix in ("", "/contacts", "/activities"):
        assert f.client.get(path + suffix, headers=foreign).status_code == 404
    assert f.client.get("/api/v1/companies", headers=foreign).json()["items"] == []
    for filters in (
        {"query": "NORTHERN"},
        {"role": "SUPPLIER"},
        {"query": "Northern", "role": "CUSTOMER"},
    ):
        response = f.client.get("/api/v1/companies", headers=foreign, params=filters)
        assert response.status_code == 200
        assert response.json() == {"items": [], "has_more": False, "next_cursor": None}
    role = f.client.post(path + "/roles", headers=foreign, json={"role": "AGENT"})
    assert role.status_code == 404
    assert role.json()["code"] == "COMPANY_NOT_FOUND"
    assert f.client.get(f"/api/v1/companies?cursor={row['id']}", headers=foreign).status_code == 404
    assert (
        f.client.post(
            path + "/contacts", headers=foreign, json={"full_name": "Foreign"}
        ).status_code
        == 404
    )
    assert (
        f.client.put(
            path,
            headers=foreign,
            json={"name": "Foreign", "expected_version": 1, "reason": "Forbidden"},
        ).status_code
        == 404
    )
    assert (
        f.client.post(
            "/api/v1/companies",
            headers=headers(f, subject="quotation-finance"),
            json={"name": "Denied", "roles": ["SUPPLIER"]},
        ).status_code
        == 403
    )
    assert table_counts(f) == before
    assert f.client.get(path, headers=headers(f)).json() == row
    _, opportunity_id = create_opportunity(f)
    # Existing converted customer/contact remain distinct from this supplier company.
    from app.crm.models import Opportunity

    with f.session_factory() as session:
        other = session.get(Opportunity, UUID(opportunity_id))
        other_contact = str(other.contact_id)
    assert f.client.get(path + f"/contacts/{other_contact}", headers=headers(f)).status_code == 404
    assert (
        f.client.put(
            path + f"/contacts/{other_contact}",
            headers=headers(f),
            json={"full_name": "Wrong parent", "expected_version": 1, "reason": "Wrong"},
        ).status_code
        == 404
    )


def test_foreign_contact_detail_update_and_cursor_preserve_original(quotation_fixture):
    f = quotation_fixture
    company = create(f)
    parent = f"/api/v1/companies/{company['id']}"
    created = f.client.post(
        parent + "/contacts",
        headers=headers(f, "scoped-contact"),
        json={"full_name": "Protected contact", "email": "protected@example.test"},
    )
    assert created.status_code == 201, created.text
    contact = created.json()
    path = parent + f"/contacts/{contact['id']}"
    foreign = headers(f, "foreign-contact", "quotation-other", f.organization_b)
    other_company = f.client.post(
        "/api/v1/companies",
        headers=foreign,
        json={"name": "Other organization company", "roles": ["CUSTOMER"]},
    )
    assert other_company.status_code == 201, other_company.text
    other_parent = f"/api/v1/companies/{other_company.json()['id']}"
    before = table_counts(f)

    assert f.client.get(path, headers=foreign).status_code == 404
    changed = f.client.put(
        path,
        headers=foreign,
        json={
            "full_name": "Forbidden replacement",
            "expected_version": contact["version"],
            "reason": "Cross organization must fail",
        },
    )
    assert changed.status_code == 404
    for target in (parent, other_parent):
        response = f.client.get(
            target + "/contacts", headers=foreign, params={"cursor": contact["id"]}
        )
        assert response.status_code == 404
    visible = f.client.get(other_parent + "/contacts", headers=foreign)
    assert visible.status_code == 200
    assert visible.json()["items"] == []
    original = f.client.get(path, headers=headers(f))
    assert original.status_code == 200
    assert original.json() == contact
    assert table_counts(f) == before
    with f.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Contact)) == 1


@pytest.mark.parametrize("recorder", [Activity, AuditRecorder, OutboxRecorder])
@pytest.mark.parametrize("kind", ["company", "contact"])
def test_archive_writes_roll_back_on_evidence_failure(
    quotation_fixture, monkeypatch, recorder, kind
):
    f = quotation_fixture
    company = create(f)
    before = table_counts(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("archive failure")

    if recorder is Activity:
        original = Session.add

        def add(session, row, *args, **kwargs):
            if isinstance(row, Activity):
                fail()
            return original(session, row, *args, **kwargs)

        monkeypatch.setattr(Session, "add", add)
    else:
        monkeypatch.setattr(recorder, "record", fail)
    service = CompanyArchiveService(f.session_factory)
    with pytest.raises(RuntimeError, match="archive failure"):
        if kind == "company":
            service.write_company(
                context,
                {
                    "name": "Rollback name",
                    "expected_version": company["version"],
                    "reason": "Failure",
                },
                key="rollback",
                company_id=UUID(company["id"]),
            )
        else:
            service.write_contact(
                context, UUID(company["id"]), {"full_name": "Rollback contact"}, key="rollback"
            )
    assert table_counts(f) == before
    assert f.client.get(f"/api/v1/companies/{company['id']}", headers=headers(f)).json() == company
    with f.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Contact)) == 0


def test_concurrent_duplicate_company_creation_and_previous_data_migration(quotation_fixture):
    f = quotation_fixture
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )

    def run(index):
        try:
            CompanyArchiveService(f.session_factory).write_company(
                context, {"name": "One company", "roles": ["SUPPLIER"]}, key=f"create-{index}"
            )
            return "ok"
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, range(2))) == ["COMPANY_NAME_EXISTS", "ok"]
    before = f.client.get("/api/v1/companies", headers=headers(f)).json()
    config = alembic_config(f.engine.url.render_as_string(hide_password=False))
    verify_legacy_upgrade(f.engine, "20260906_0014")
    command.check(config)
    assert f.client.get("/api/v1/companies", headers=headers(f)).json() == before
    with f.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 1
