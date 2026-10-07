"""
Domain enums for the AnyCompany Hotel platform.

All enums inherit from (str, Enum) so they serialize cleanly to JSON
and can be compared directly with string values.
"""

from enum import StrEnum


class ReservationStatus(StrEnum):
    """Status of a hotel reservation throughout its lifecycle."""
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class RoomStatus(StrEnum):
    """Housekeeping / operational status of a physical room."""
    CLEAN = "CLEAN"
    DIRTY = "DIRTY"
    INSPECTED = "INSPECTED"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    OUT_OF_INVENTORY = "OUT_OF_INVENTORY"


class PaymentStatus(StrEnum):
    """Status of a Stripe PaymentIntent through the capture lifecycle."""
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    VOIDED = "VOIDED"
    EXPIRED = "EXPIRED"


class RefundStatus(StrEnum):
    """Status of a Stripe refund."""
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class DiscountType(StrEnum):
    """Type of discount applied to a rate or charge."""
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"


class CartStatus(StrEnum):
    """Status of a booking cart in the Booking Engine."""
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CONVERTED = "CONVERTED"


class ChannelMethod(StrEnum):
    """Channel through which a reservation was made."""
    WEB = "WEB"
    MOBILE_APP = "MOBILE_APP"
    PHONE = "PHONE"
    GDS = "GDS"
    OTA = "OTA"
    WALKIN = "WALKIN"


class RatePlanType(StrEnum):
    """Type of rate plan offered."""
    PUBLIC = "PUBLIC"
    NEGOTIATED = "NEGOTIATED"
    LOYALTY = "LOYALTY"
    PACKAGE = "PACKAGE"
    PROMOTIONAL = "PROMOTIONAL"


class CancellationPolicy(StrEnum):
    """Cancellation policy tier for a rate plan."""
    FLEXIBLE = "FLEXIBLE"
    MODERATE = "MODERATE"
    STRICT = "STRICT"
    NON_REFUNDABLE = "NON_REFUNDABLE"


class GuaranteeType(StrEnum):
    """Method used to guarantee a reservation."""
    CREDIT_CARD = "CREDIT_CARD"
    DEPOSIT = "DEPOSIT"
    CORPORATE = "CORPORATE"


class TripType(StrEnum):
    """Purpose of the guest's trip."""
    LEISURE = "LEISURE"
    BUSINESS = "BUSINESS"
    GROUP = "GROUP"
    OTHER = "OTHER"


# ==============================================================================
# PMS Enums (added for PMS expansion)
# ==============================================================================


class TaskType(StrEnum):
    """Type of housekeeping task."""
    CHECKOUT = "CHECKOUT"
    PRE_ARRIVAL = "PRE_ARRIVAL"
    MAINTENANCE = "MAINTENANCE"


class TaskPriority(StrEnum):
    """Priority level for housekeeping tasks."""
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class TaskStatus(StrEnum):
    """Status of a housekeeping task through its lifecycle."""
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    CLEANING = "CLEANING"
    COMPLETED = "COMPLETED"
    INSPECTING = "INSPECTING"
    INSPECTED = "INSPECTED"
    FAILED = "FAILED"


class FolioStatus(StrEnum):
    """Status of a billing folio through its lifecycle."""
    OPEN = "OPEN"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    VOID = "VOID"
    PAYMENT_FAILED = "PAYMENT_FAILED"


class ChargeType(StrEnum):
    """Type of charge posted to a folio."""
    ROOM_RATE = "ROOM_RATE"
    TAX = "TAX"
    SERVICE = "SERVICE"
    ADJUSTMENT = "ADJUSTMENT"


class LoyaltyTier(StrEnum):
    """Guest loyalty tier levels."""
    NONE = "NONE"
    SILVER = "SILVER"
    GOLD = "GOLD"
    DIAMOND = "DIAMOND"


class LoyaltyTransactionType(StrEnum):
    """Type of loyalty point transaction."""
    EARN_STAY = "EARN_STAY"
    REDEEM_NIGHT = "REDEEM_NIGHT"
    ADJUSTMENT = "ADJUSTMENT"


class RecordType(StrEnum):
    """Type of check-in/out record."""
    CHECKIN = "CHECKIN"
    CHECKOUT = "CHECKOUT"


class PmsRoomStatus(StrEnum):
    """Extended room status for PMS operations (superset of CRS RoomStatus)."""
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    DIRTY = "DIRTY"
    CLEANING = "CLEANING"
    INSPECTING = "INSPECTING"
    OUT_OF_ORDER = "OUT_OF_ORDER"


class StaffRole(StrEnum):
    """Cognito group names for staff roles."""
    ADMIN = "Admin"
    MANAGER = "Manager"
    FRONT_DESK = "FrontDesk"
    HOUSEKEEPING = "Housekeeping"
    REGIONAL_MANAGER = "RegionalManager"
    REVENUE_MANAGER = "RevenueManager"
