from app import models as application_models
from app.core.database import Base
from app.core.database_types import exchange_rate_type, money_type, quantity_type
from sqlalchemy import DateTime, Float, Numeric


def test_canonical_decimal_types_use_required_precision() -> None:
    money = money_type()
    quantity = quantity_type()
    exchange_rate = exchange_rate_type()

    assert isinstance(money, Numeric)
    assert (money.precision, money.scale) == (18, 4)
    assert (quantity.precision, quantity.scale) == (18, 4)
    assert (exchange_rate.precision, exchange_rate.scale) == (18, 8)


def test_mapped_tables_use_timezone_aware_timestamps_and_no_float() -> None:
    _ = application_models

    for table in Base.metadata.tables.values():
        for column in table.columns:
            assert not isinstance(column.type, Float)
            if column.name.endswith("_at"):
                assert isinstance(column.type, DateTime)
                assert column.type.timezone is True
