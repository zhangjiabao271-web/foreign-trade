from enum import StrEnum


class CompanyRoleType(StrEnum):
    CUSTOMER = "CUSTOMER"
    SUPPLIER = "SUPPLIER"
    FORWARDER = "FORWARDER"
    AGENT = "AGENT"
