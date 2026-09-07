from enum import StrEnum


class ShipmentStatus(StrEnum):
    PLANNING = "PLANNING"
    BOOKED = "BOOKED"
    READY = "READY"
    CUSTOMS = "CUSTOMS"
    DEPARTED = "DEPARTED"
    IN_TRANSIT = "IN_TRANSIT"
    ARRIVED = "ARRIVED"
    DELIVERED = "DELIVERED"
