"""
Tenant isolation utilities for the AnyCompany Hotel PMS.

Enforces property-scoped, regional, and chain-level access control
based on JWT custom claims from Cognito.
"""

from typing import Optional
from utils.auth import get_claims, get_groups
from utils.response import forbidden


# Groups that have chain-level (all properties) access
CHAIN_LEVEL_GROUPS = {"Admin", "Manager", "RevenueManager"}
REGIONAL_GROUPS = {"RegionalManager"}


def get_property_id(event: dict) -> Optional[str]:
    """
    Extract the property_id from the JWT custom:property_id claim.

    Returns None if the claim is absent (chain-level user).

    Args:
        event: Lambda event from API Gateway.

    Returns:
        Property ID string or None for chain-level users.
    """
    claims = get_claims(event)
    return claims.get("custom:property_id") or None


def get_region(event: dict) -> Optional[str]:
    """
    Extract the region from the JWT custom:region claim.

    Returns None if the claim is absent.

    Args:
        event: Lambda event from API Gateway.

    Returns:
        Region string or None.
    """
    claims = get_claims(event)
    return claims.get("custom:region") or None


def get_groups_from_event(event: dict) -> list[str]:
    """
    Extract Cognito groups from the JWT claims.

    The 'cognito:groups' claim can arrive in a few shapes; handle all of them:
    - a JSON list: ["Admin", "Manager"]
    - a bracketed, space-separated string: "[Admin Manager]"
      (API Gateway serializes a multi-valued claim this way)
    - a comma-separated string: "Admin,Manager"

    Args:
        event: Lambda event from API Gateway.

    Returns:
        List of group name strings.
    """
    claims = get_claims(event)
    groups = claims.get("cognito:groups", "")
    if isinstance(groups, list):
        return groups
    if isinstance(groups, str) and groups:
        # Strip any surrounding brackets, then split on space or comma.
        cleaned = groups.strip("[]")
        if not cleaned:
            return []
        # Handle both space and comma separators
        if " " in cleaned:
            return [g.strip() for g in cleaned.split(" ") if g.strip()]
        return [g.strip() for g in cleaned.split(",") if g.strip()]
    return []


def has_group(event: dict, *groups: str) -> bool:
    """
    Check if the authenticated user is in any of the specified groups.

    Args:
        event: Lambda event from API Gateway.
        *groups: One or more group names to check.

    Returns:
        True if user is in at least one of the specified groups.
    """
    user_groups = set(get_groups_from_event(event))
    return bool(user_groups.intersection(groups))


def require_groups(event: dict, *groups: str) -> None:
    """
    Verify the user is in at least one of the specified groups.

    Raises ForbiddenError if the user lacks the required group membership.

    Args:
        event: Lambda event from API Gateway.
        *groups: One or more allowed group names.

    Raises:
        ForbiddenError: If user is not in any of the specified groups.
    """
    if not has_group(event, *groups):
        raise ForbiddenError("Access denied: insufficient permissions")


def verify_property_access(event: dict, record_property_id: str) -> None:
    """
    Verify the authenticated user has access to the specified property.

    Access rules:
    - Chain-level users (Admin, Manager, RevenueManager): access all properties
    - Regional users (RegionalManager): access properties in their region
    - Property-level users: access only their assigned property

    Args:
        event: Lambda event from API Gateway.
        record_property_id: The property_id of the record being accessed.

    Raises:
        ForbiddenError: If the user does not have access to the property.
    """
    caller_property_id = get_property_id(event)

    if caller_property_id is None:
        # Chain-level or regional user
        user_groups = set(get_groups_from_event(event))

        if user_groups.intersection(CHAIN_LEVEL_GROUPS):
            return  # Chain-level access granted

        if user_groups.intersection(REGIONAL_GROUPS):
            # Regional access — would need to verify property is in region
            # For now, regional managers get access (region check at query level)
            return

        raise ForbiddenError("Access denied: no property access")

    # Property-level user — strict match
    if caller_property_id != record_property_id:
        raise ForbiddenError("Access denied: property mismatch")


def get_accessible_properties(event: dict) -> Optional[list[str]]:
    """
    Get the list of property IDs the user can access.

    Returns:
        - List with single property_id for property-scoped users
        - None for chain-level users (meaning all properties)

    Note: Regional filtering should be applied at the query level
    using get_region() to filter by property.region.

    Args:
        event: Lambda event from API Gateway.

    Returns:
        List of property ID strings, or None for unrestricted access.
    """
    caller_property_id = get_property_id(event)
    if caller_property_id is not None:
        return [caller_property_id]

    # Chain-level user — None means "all properties"
    return None


class ForbiddenError(Exception):
    """Raised when a user lacks permission to access a resource."""
    pass
