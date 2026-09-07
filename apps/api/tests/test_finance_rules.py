from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.finance.enums import ReceivableStatus
from app.finance.models import Receivable
from app.finance.schemas import PaymentReverse, SalesOrderComplete
from app.finance.services import status_for_receivable
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("days", "paid", "expected"),
    [
        (1, "0", ReceivableStatus.PENDING),
        (0, "0", ReceivableStatus.DUE),
        (-1, "0", ReceivableStatus.OVERDUE),
        (-1, "0.0001", ReceivableStatus.PARTIALLY_PAID),
        (1, "10", ReceivableStatus.PAID),
    ],
)
def test_receivable_state_uses_explicit_organization_business_day(days, paid, expected):
    today = date(2026, 9, 5)
    row = Receivable(amount=Decimal("10"), due_date=today + timedelta(days=days))
    assert status_for_receivable(row, Decimal(paid), today=today) == expected


def test_whitespace_cannot_authorize_financial_waiver_or_reversal():
    with pytest.raises(ValidationError):
        PaymentReverse(reason="     ")
    with pytest.raises(ValidationError):
        SalesOrderComplete(expected_version=1, financial_waiver_reason="          ")
