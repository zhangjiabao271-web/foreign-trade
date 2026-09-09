from dataclasses import replace
from uuid import uuid4

import pytest
from app.auth.errors import ApiProblem
from app.platform.models import AsyncJob, OutboxEvent
from app.platform.repositories import AsyncJobRepository, OutboxEventRepository
from app.platform.services import AsyncJobQueryService, OutboxAdminService
from test_document_review import reviewer
from test_sales_foreign_commands import foreign_manager

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def test_platform_direct_queries_scope_jobs_and_dead_events(quotation_fixture):
    f = quotation_fixture
    _, owner = reviewer(f)
    foreign = foreign_manager(f)
    with f.session_factory.begin() as session:
        job = AsyncJob(organization_id=f.organization_a, job_type="fixture", correlation_id=uuid4())
        event = OutboxEvent(
            organization_id=f.organization_a,
            event_type="fixture.v1",
            aggregate_type="fixture",
            aggregate_id=uuid4(),
            correlation_id=uuid4(),
            status="DEAD",
        )
        session.add_all([job, event])
        session.flush()
        job_id, event_id = job.id, event.id
    with f.session_factory() as session:
        jobs = AsyncJobRepository(session)
        events = OutboxEventRepository(session)
        service = AsyncJobQueryService(jobs)
        for context, present in ((owner, True), (foreign, False)):
            org = context.organization_id
            assert (jobs.get(organization_id=org, record_id=job_id) is not None) is present
            assert len(jobs.list(organization_id=org)) == int(present)
            assert jobs.count(organization_id=org) == int(present)
            assert (
                events.get_for_update(organization_id=org, record_id=event_id) is not None
            ) is present
            assert len(events.list_dead(organization_id=org)) == int(present)
            assert len(service.list(context)) == int(present)
            assert service.count(context) == int(present)
        assert service.get(owner, job_id).id == job_id
        with pytest.raises(ApiProblem) as denied:
            service.get(foreign, job_id)
        assert denied.value.status == 404
        no_permissions = replace(owner, permissions=frozenset())
        for call in (
            lambda: service.get(no_permissions, job_id),
            lambda: service.list(no_permissions),
            lambda: service.count(no_permissions),
            lambda: OutboxAdminService(events).list_dead(no_permissions),
        ):
            with pytest.raises(ApiProblem) as denied:
                call()
            assert denied.value.status == 403
        assert not session.dirty
