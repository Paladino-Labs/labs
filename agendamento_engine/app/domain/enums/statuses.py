from enum import Enum


class FinancialStatus(str, Enum):
    UNPAID = "UNPAID"
    PAID = "PAID"
    REFUNDED = "REFUNDED"


class AvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BOOKED = "BOOKED"
    BLOCKED = "BLOCKED"


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    PROFESSIONAL = "PROFESSIONAL"
    CLIENT = "CLIENT"
