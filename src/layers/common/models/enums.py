"""
Domain enums for the AnyCompany Hotel platform.

All enums inherit from (str, Enum) so they serialize cleanly to JSON
and can be compared directly with string values.
"""

from enum import Enum


class ReservationStatus(str, Enum):
    """Status of a hotel reservation throughout its lifecycle."""
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class RoomStatus(str, Enum):
    """Housekeeping / operational status of a physical room."""
    CLEAN = "CLEAN"
    DIRTY = "DIRTY"
    INSPECTED = "INSPECTED"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    OUT_OF_INVENTORY = "OUT_OF_INVENTORY"


class PaymentStatus(str, Enum):
    """Status of a Stripe PaymentIntent through the capture lifecycle."""
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    VOIDED = "VOIDED"
    EXPIRED = "EXPIRED"


class RefundStatus(str, Enum):
    """Status of a Stripe refund."""
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class DiscountType(str, Enum):
    """Type of discount applied to a rate or charge."""
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"


class CartStatus(str, Enum):
    """Status of a booking cart in the Booking Engine."""
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CONVERTED = "CONVERTED"


class ChannelMethod(str, Enum):
    """Channel through which a reservation was made."""
    WEB = "WEB"
    MOBILE_APP = "MOBILE_APP"
    PHONE = "PHONE"
    GDS = "GDS"
    OTA = "OTA"
    WALKIN = "WALKIN"


class RatePlanType(str, Enum):
    """Type of rate plan offered."""
    PUBLIC = "PUBLIC"
    NEGOTIATED = "NEGOTIATED"
    LOYALTY = "LOYALTY"
    PACKAGE = "PACKAGE"
    PROMOTIONAL = "PROMOTIONAL"


class CancellationPolicy(str, Enum):
    """Cancellation policy tier for a rate plan."""
    FLEXIBLE = "FLEXIBLE"
    MODERATE = "MODERATE"
    STRICT = "STRICT"
    NON_REFUNDABLE = "NON_REFUNDABLE"


class GuaranteeType(str, Enum):
    """Method used to guarantee a reservation."""
    CREDIT_CARD = "CREDIT_CARD"
    DEPOSIT = "DEPOSIT"
    CORPORATE = "CORPORATE"


class TripType(str, Enum):
    """Purpose of the guest's trip."""
    LEISURE = "LEISURE"
    BUSINESS = "BUSINESS"
    GROUP = "GROUP"
    OTHER = "OTHER"


# ==============================================================================
# PMS Enums (added for PMS expansion)
# ==============================================================================


class TaskType(str, Enum):
    """Type of housekeeping task."""
    CHECKOUT = "CHECKOUT"
    PRE_ARRIVAL = "PRE_ARRIVAL"
    MAINTENANCE = "MAINTENANCE"


class TaskPriority(str, Enum):
    """Priority level for housekeeping tasks."""
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class TaskStatus(str, Enum):
    """Status of a housekeeping task through its lifecycle."""
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    CLEANING = "CLEANING"
    COMPLETED = "COMPLETED"
    INSPECTING = "INSPECTING"
    INSPECTED = "INSPECTED"
    FAILED = "FAILED"


class FolioStatus(str, Enum):
    """Status of a billing folio through its lifecycle."""
    OPEN = "OPEN"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    VOID = "VOID"
    PAYMENT_FAILED = "PAYMENT_FAILED"


class ChargeType(str, Enum):
    """Type of charge posted to a folio."""
    ROOM_RATE = "ROOM_RATE"
    TAX = "TAX"
    SERVICE = "SERVICE"
    ADJUSTMENT = "ADJUSTMENT"


class LoyaltyTier(str, Enum):
    """Guest loyalty tier levels."""
    NONE = "NONE"
    SILVER = "SILVER"
    GOLD = "GOLD"
    DIAMOND = "DIAMOND"


class LoyaltyTransactionType(str, Enum):
    """Type of loyalty point transaction."""
    EARN_STAY = "EARN_STAY"
    REDEEM_NIGHT = "REDEEM_NIGHT"
    ADJUSTMENT = "ADJUSTMENT"


class RecordType(str, Enum):
    """Type of check-in/out record."""
    CHECKIN = "CHECKIN"
    CHECKOUT = "CHECKOUT"


class PmsRoomStatus(str, Enum):
    """Extended room status for PMS operations (superset of CRS RoomStatus)."""
    AVAILABLE = "AVAILABLE"
    OCCUPIED = "OCCUPIED"
    DIRTY = "DIRTY"
    CLEANING = "CLEANING"
    INSPECTING = "INSPECTING"
    OUT_OF_ORDER = "OUT_OF_ORDER"


class StaffRole(str, Enum):
    """Cognito group names for staff roles."""
    ADMIN = "Admin"
    MANAGER = "Manager"
    FRONT_DESK = "FrontDesk"
    HOUSEKEEPING = "Housekeeping"
    REGIONAL_MANAGER = "RegionalManager"
    REVENUE_MANAGER = "RevenueManager"
