"""
The contract request matrix.

A single declarative list of (api, method, path, role, body, expected status
class, structural assertions). Both capture.py and test_contract.py consume
this so the captured baseline and each replay test the SAME requests.

Each entry is a dict:
    name:     unique snapshot key
    api:      "crs" | "pms"
    method:   HTTP method
    path:     request path (already containing any concrete ids resolved at
              runtime via {placeholders} — see capture.py's resolver)
    role:     test-user role for auth, or None for an unauthenticated call
    body:     request body dict (for POST/PUT) or None
    expect:   expected HTTP status (the contract)
    shape:    optional list of dotted key paths that MUST be present in the
              response body (structural contract, value-independent)

Placeholders resolved at runtime by capture/verify:
    {propertyId}  -> a real active property id
    {roomTypeId}  -> a room type under that property
    {guestId}     -> the testsuite-guest's guest id (created on demand)

The matrix deliberately covers: public reads, auth-required rejections,
role-based 403s, pagination envelopes, and not-found shapes — the
behaviors most likely to drift if the API changes.
"""

from datetime import date, timedelta

# Relative stay window for availability searches. A hardcoded date rots once it
# passes: the API correctly answers 400 ("check_in date must be today or in the
# future"), which reads as contract drift but is only a stale input. Shapes are
# value-independent, so moving the window doesn't touch the baseline.
_CHECK_IN = str(date.today() + timedelta(days=30))
_CHECK_OUT = str(date.today() + timedelta(days=32))

MATRIX = [
    # ---- Public CRS reads (no token) ----
    {
        "name": "crs_list_properties_public",
        "api": "crs", "method": "GET", "path": "/properties?limit=2",
        "role": None, "body": None, "expect": 200,
        "shape": ["success", "data", "metadata.pagination"],
    },
    {
        "name": "crs_get_property",
        "api": "crs", "method": "GET", "path": "/properties/{propertyId}",
        "role": None, "body": None, "expect": 200,
        "shape": ["success", "data.roomTypes"],
    },
    {
        "name": "crs_get_property_bad_uuid",
        "api": "crs", "method": "GET", "path": "/properties/not-a-uuid",
        "role": None, "body": None, "expect": 400,
        "shape": ["success", "error.code"],
    },
    {
        "name": "crs_get_property_not_found",
        "api": "crs", "method": "GET",
        "path": "/properties/00000000-0000-4000-8000-000000000000",
        "role": None, "body": None, "expect": 404,
        "shape": ["success", "error.code"],
    },
    {
        "name": "crs_list_room_types",
        "api": "crs", "method": "GET",
        "path": "/properties/{propertyId}/room-types",
        "role": None, "body": None, "expect": 200,
        "shape": ["success", "data"],
    },
    {
        "name": "crs_booking_search",
        "api": "crs", "method": "POST", "path": "/booking/search",
        "role": None,
        "body": {"checkIn": _CHECK_IN, "checkOut": _CHECK_OUT, "adults": 2, "limit": 3},
        "expect": 200,
        "shape": ["success", "data"],
    },
    {
        "name": "crs_booking_search_missing_dates",
        "api": "crs", "method": "POST", "path": "/booking/search",
        "role": None, "body": {"adults": 2}, "expect": 400,
        "shape": ["success", "error.code"],
    },
    {
        "name": "crs_availability_missing_property",
        "api": "crs", "method": "GET", "path": "/availability",
        "role": None, "body": None, "expect": 400,
        "shape": ["success", "error.code"],
    },

    # ---- CRS auth-required ----
    {
        "name": "crs_list_reservations_requires_auth",
        "api": "crs", "method": "GET", "path": "/reservations",
        "role": None, "body": None, "expect": 401,
    },
    {
        "name": "crs_list_reservations_as_guest",
        "api": "crs", "method": "GET", "path": "/reservations",
        "role": "guest", "body": None, "expect": 400,
        # guest test user has no DB guest row -> "Guest profile not found" 400.
        "shape": ["success", "error.code"],
    },

    # ---- PMS auth-required + role matrix ----
    {
        "name": "pms_stays_requires_auth",
        "api": "pms", "method": "GET", "path": "/stays",
        "role": None, "body": None, "expect": 401,
    },
    {
        "name": "pms_stays_admin",
        "api": "pms", "method": "GET", "path": "/stays?limit=5",
        "role": "admin", "body": None, "expect": 200,
        "shape": ["success", "data"],
    },
    {
        "name": "pms_stays_housekeeping_forbidden",
        "api": "pms", "method": "GET", "path": "/stays?limit=5",
        "role": "housekeeping", "body": None, "expect": 403,
        "shape": ["success", "error.code"],
    },
    {
        "name": "pms_tasks_housekeeping_ok",
        "api": "pms", "method": "GET", "path": "/housekeeping/tasks?limit=5",
        "role": "housekeeping", "body": None, "expect": 200,
        "shape": ["success", "data"],
    },
    {
        "name": "pms_folios_admin",
        "api": "pms", "method": "GET", "path": "/billing/folios?limit=5",
        "role": "admin", "body": None, "expect": 200,
        "shape": ["success", "data"],
    },
    {
        "name": "pms_post_charge_frontdesk_forbidden",
        "api": "pms", "method": "POST",
        "path": "/billing/folios/00000000-0000-4000-8000-000000000000/charges",
        "role": "frontdesk", "body": {"amount": 10, "description": "T"}, "expect": 403,
        "shape": ["success", "error.code"],
    },
    {
        "name": "pms_loyalty_adjust_frontdesk_forbidden",
        "api": "pms", "method": "POST",
        "path": "/loyalty/00000000-0000-4000-8000-000000000000/adjust",
        "role": "frontdesk", "body": {"points": 50, "reason": "t"}, "expect": 403,
        "shape": ["success", "error.code"],
    },
    {
        "name": "pms_occupancy_admin",
        "api": "pms", "method": "GET", "path": "/reporting/occupancy",
        "role": "admin", "body": None, "expect": 200,
        "shape": ["success", "data"],
    },
    {
        "name": "pms_occupancy_housekeeping_forbidden",
        "api": "pms", "method": "GET", "path": "/reporting/occupancy",
        "role": "housekeeping", "body": None, "expect": 403,
        "shape": ["success", "error.code"],
    },
]


# Volatile response fields stripped before snapshotting/diffing. These legitimately
# vary run-to-run and are NOT part of the contract.
VOLATILE_KEYS = {
    "requestId",      # uuid per response
    "timestamp",      # response time
    "publishedAt",
    "correlationId",
}
