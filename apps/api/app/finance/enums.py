from enum import StrEnum


class ReceivableStatus(StrEnum):
    PENDING = "PENDING"
    DUE = "DUE"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"


class ReceivableInstallmentType(StrEnum):
    DEPOSIT = "DEPOSIT"
    BALANCE = "BALANCE"


class PaymentKind(StrEnum):
    RECEIPT = "RECEIPT"
    REVERSAL = "REVERSAL"


class PaymentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVERSED = "REVERSED"


class PaymentMethod(StrEnum):
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD = "CARD"
    CASH = "CASH"
    OTHER = "OTHER"


class AllocationKind(StrEnum):
    ALLOCATION = "ALLOCATION"
    REVERSAL = "REVERSAL"
