from enum import StrEnum


class InquiryStatus(StrEnum):
    OPEN = "OPEN"
    QUOTING = "QUOTING"
    CLOSED = "CLOSED"
