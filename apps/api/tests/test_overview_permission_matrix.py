from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.work.overview import OverviewQueryService, QueueKind


@pytest.mark.parametrize(
    "queue,domain",
    [
        (QueueKind.LEADS, Permission.LEAD_READ),
        (QueueKind.QUOTATIONS, Permission.QUOTATION_READ),
        (QueueKind.DEPOSITS, Permission.ORDER_READ),
        (QueueKind.PREPARATION, Permission.ORDER_READ),
        (QueueKind.SHIPMENTS, Permission.SHIPMENT_READ),
        (QueueKind.RECEIVABLES, Permission.RECEIVABLE_READ),
        (QueueKind.CUSTOMS, Permission.EXPORT_READ),
        (QueueKind.REFUNDS, Permission.EXPORT_READ),
    ],
)
@pytest.mark.parametrize("missing_overview", [False, True])
def test_each_queue_requires_both_permissions_before_database_access(
    queue, domain, missing_overview
):
    permissions = {domain} if missing_overview else {Permission.OVERVIEW_READ}
    context = RequestContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        request_id=uuid4(),
        permissions=frozenset(permissions),
    )
    # A denied request must never attempt even the organization-date database lookup.
    with pytest.raises(ApiProblem) as denied:
        OverviewQueryService(None).page(context, queue, offset=0, limit=20)
    assert denied.value.status == 403
    assert denied.value.code == "PERMISSION_DENIED"
