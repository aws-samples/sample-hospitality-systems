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
    ForbiddenError,
    require_groups,
    resolve_property_scope,
)

logger = get_logger("pms-reporting")


@logger.inject_lambda_context
def handler(event, context):
    try:
        require_groups(
            event,
            "FrontDesk", "Housekeeping", "Manager", "Admin", "RevenueManager", "RegionalManager",
        )

        # Derives the caller's level from the group claim and only ever narrows
        # with the attribute claims. A caller with neither a property claim nor
        # a qualifying group is denied, and a regional caller with no region
        # claim is denied rather than shown the whole estate.
        scope = resolve_property_scope(event)

        with get_conn() as conn, conn.cursor() as cur:
            if scope.property_id:
                # Property-scoped user: only their property.
                cur.execute(
                    "SELECT property_id, name, city, state, region "
                    "FROM properties WHERE property_id = %s AND is_active = TRUE",
                    [scope.property_id],
                )
            elif scope.region:
                # Regional user: properties in their region.
                cur.execute(
                    "SELECT property_id, name, city, state, region "
                    "FROM properties WHERE region = %s AND is_active = TRUE ORDER BY name",
                    [scope.region],
                )
            else:
                # Chain-level: all active properties.
                cur.execute(
                    "SELECT property_id, name, city, state, region "
                    "FROM properties WHERE is_active = TRUE ORDER BY name"
                )

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
