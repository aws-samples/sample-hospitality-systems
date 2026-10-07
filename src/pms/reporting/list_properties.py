"""
PMS List Accessible Properties.

GET /properties
Lists active properties that the authenticated staff user can access:
- Chain-level users (Admin/Manager/RevenueManager): all active properties.
- Regional users (RegionalManager): properties in their assigned region.
- Property-scoped users (FrontDesk/Housekeeping): just their one property.

Used by the PMS Dashboard to populate the property selector for chain-level
users and to resolve the property name for property-scoped users.
"""

from utils.database import get_conn
from utils.logger import get_logger
from utils.response import forbidden, ok, server_error
from utils.tenant import (
    CHAIN_LEVEL_GROUPS,
    REGIONAL_GROUPS,
    ForbiddenError,
    get_groups_from_event,
    get_property_id,
    get_region,
    require_groups,
)

logger = get_logger("pms-reporting")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(
            event,
            "FrontDesk", "Housekeeping", "Manager", "Admin", "RevenueManager", "RegionalManager",
        )

        caller_property_id = get_property_id(event)
        user_groups = set(get_groups_from_event(event))

        with get_conn() as conn, conn.cursor() as cur:
            if caller_property_id:
                # Property-scoped user: only their property.
                cur.execute(
                    "SELECT property_id, name, city, state, region "
                    "FROM properties WHERE property_id = %s AND is_active = TRUE",
                    [caller_property_id],
                )
            elif user_groups.intersection(REGIONAL_GROUPS):
                # Regional user: properties in their region.
                region = get_region(event)
                if not region:
                    cur.execute(
                        "SELECT property_id, name, city, state, region "
                        "FROM properties WHERE is_active = TRUE ORDER BY name"
                    )
                else:
                    cur.execute(
                        "SELECT property_id, name, city, state, region "
                        "FROM properties WHERE region = %s AND is_active = TRUE ORDER BY name",
                        [region],
                    )
            elif user_groups.intersection(CHAIN_LEVEL_GROUPS):
                # Chain-level: all active properties.
                cur.execute(
                    "SELECT property_id, name, city, state, region "
                    "FROM properties WHERE is_active = TRUE ORDER BY name"
                )
            else:
                return ok({"properties": []})

            rows = cur.fetchall()

        properties = [
            {
                "propertyId": str(r["property_id"]),
                "name": r["name"],
                "city": r["city"],
                "state": r["state"],
                "region": r.get("region"),
            }
            for r in rows
        ]

        return ok({"properties": properties})

    except ForbiddenError as e:
        return forbidden(str(e))
    except Exception:
        logger.exception("Error listing accessible properties")
        return server_error()
