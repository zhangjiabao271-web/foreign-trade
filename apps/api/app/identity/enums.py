from enum import StrEnum


class OrganizationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class MembershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INVITED = "INVITED"
    DISABLED = "DISABLED"


class MembershipRole(StrEnum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    SALES = "SALES"
    OPERATIONS = "OPERATIONS"
    FINANCE = "FINANCE"
    VIEWER = "VIEWER"
