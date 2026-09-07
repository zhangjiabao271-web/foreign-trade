from enum import StrEnum


class LeadStatus(StrEnum):
    NEW = "NEW"
    QUALIFIED = "QUALIFIED"
    CONTACTED = "CONTACTED"
    RESPONDED = "RESPONDED"
    NO_RESPONSE = "NO_RESPONSE"
    CONVERTED = "CONVERTED"
    DISQUALIFIED = "DISQUALIFIED"


class OpportunityStatus(StrEnum):
    OPEN = "OPEN"
    INQUIRY = "INQUIRY"
    QUOTING = "QUOTING"
    NEGOTIATION = "NEGOTIATION"
    WON = "WON"
    LOST = "LOST"
