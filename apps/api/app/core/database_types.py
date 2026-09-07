from decimal import Decimal

from sqlalchemy import Numeric

MONEY_PRECISION = 18
MONEY_SCALE = 4
QUANTITY_PRECISION = 18
QUANTITY_SCALE = 4
EXCHANGE_RATE_PRECISION = 18
EXCHANGE_RATE_SCALE = 8


def money_type() -> Numeric[Decimal]:
    return Numeric(MONEY_PRECISION, MONEY_SCALE)


def quantity_type() -> Numeric[Decimal]:
    return Numeric(QUANTITY_PRECISION, QUANTITY_SCALE)


def exchange_rate_type() -> Numeric[Decimal]:
    return Numeric(EXCHANGE_RATE_PRECISION, EXCHANGE_RATE_SCALE)
