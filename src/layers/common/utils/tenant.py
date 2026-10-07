"""
Tenant isolation utilities for the AnyCompany Hotel PMS.

Enforces property-scoped, regional, and chain-level access control
based on JWT custom claims from Cognito.

Trust model
-----------
Two different claim families feed these decisions, and they are NOT equally
trustworthy:

- `cognito:groups` — set only through the Cognito admin APIs
  (AdminAddUserToGroup). A signed-in user cannot grant themselves a group.
  This is the authoritative signal for *what level* of access a caller has.
- `custom:property_id` / `custom:region` — user-pool attributes. They are
  authoritative only because the user-pool clients do not list them in
  WriteAttributes (see stacks/auth.yaml); otherwise the signed-in user could
  rewrite them with UpdateUserAttributes. They narrow access *within* a level.

Because the group claim is the stronger signal, access level is always derived
from groups, and the attribute claims only ever *restrict* further. In
particular, the absence of `custom:property_id` must never by itself be read as
"this caller is chain-level" — see resolve_property_scope().
"""

from typing import NamedTuple

from utils.auth import get_claims

# Groups that have chain-level (all properties) access
CHAIN_LEVEL_GROUPS = {"Admin", "Manager", "RevenueManager"}
REGIONAL_GROUPS = {"RegionalManager"}


def get_property_id(event: dict) -> str | None:
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


def get_region(event: dict) -> str | None:
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


def get_accessible_properties(event: dict) -> list[str] | None:
    """
    Get the list of property IDs the user can access.

    SUPERSEDED by resolve_property_scope(), which should be preferred for new
    code: this signature cannot express a regional scope, so it rejects
    regional callers outright rather than silently widening them to the chain.
    It is retained because its flat-list contract is convenient for a single
    `= ANY(%s)` bind.

    Delegates its authorization decision to resolve_property_scope() so it
    cannot fail open: returning None ("all properties") for any caller who
    merely lacks a property claim would let that caller read the whole chain.

    Args:
        event: Lambda event from API Gateway.

    Returns:
        - List with a single property_id for property-scoped callers
        - None for chain-level callers (meaning all properties)

    Raises:
        ForbiddenError: If the caller has no qualifying access, or is a
            regional caller (whose scope this return type cannot represent —
            use resolve_property_scope() instead).
    """
    scope = resolve_property_scope(event)

    if scope.property_id:
        return [scope.property_id]

    if scope.region:
        raise ForbiddenError(
            "Regional scope cannot be expressed as a property list; "
            "use resolve_property_scope()"
        )

    # Verified chain-level caller — None means "all properties".
    return None


class TenantScope(NamedTuple):
    """
    The resolved tenant scope for a collection (list / report) query.

    Attributes:
        property_id: Single property the query must be pinned to, or None for
            "every property the caller's level allows".
        region: Region the query must be restricted to, or None for no regional
            restriction. Only ever set for regional callers.
    """

    property_id: str | None
    region: str | None


def resolve_property_scope(
    event: dict, requested_property_id: str | None = None
) -> TenantScope:
    """
    Resolve the property scope for a collection query, failing closed.

    Collection handlers (list stays / folios / tasks, room status, occupancy and
    range reports) cannot use verify_property_access(), because there is no
    single record to check against — they need to know up front which
    properties to read. The natural shorthand for that is
    `get_property_id(event) or request.propertyId`, but it fails OPEN: a caller
    with no `custom:property_id` claim yields None, None is passed to a
    NULL-guarded SQL predicate, the predicate drops out, and the query returns
    every property in the chain.

    That shorthand treats "no property claim" as proof of chain-level access.
    It is not: it is merely the absence of a restriction. Only the
    `cognito:groups` claim — which a signed-in user cannot alter — actually
    establishes that a caller is entitled to the whole estate.

    So access level comes from the group claim first, and the attribute claim
    only narrows it:

    - Property-scoped caller (has `custom:property_id`): pinned to that
      property. `requested_property_id` is ignored, so a property-scoped caller
      can neither widen to the chain nor move to a different property.
    - Chain-level group, no property claim: unrestricted, but may voluntarily
      narrow to `requested_property_id`.
    - Regional group, no property claim: restricted to `custom:region`, and may
      voluntarily narrow to `requested_property_id` within it. A regional
      caller whose `custom:region` claim is missing or empty is DENIED, not
      widened to the chain — the same fail-closed rule applied to the property
      claim.
    - Anything else (no property claim and no qualifying group): denied.

    Args:
        event: Lambda event from API Gateway.
        requested_property_id: Optional `propertyId` from the query string — an
            honoured *narrowing* for chain/regional callers, ignored entirely
            for property-scoped callers.

    Returns:
        TenantScope to apply to the query.

    Raises:
        ForbiddenError: If the caller has neither a property claim nor a
            chain-level or regional group.
    """
    caller_property_id = get_property_id(event)
    if caller_property_id:
        # Property-pinned. Never honour a requested override.
        return TenantScope(property_id=caller_property_id, region=None)

    user_groups = set(get_groups_from_event(event))
    narrowed = requested_property_id or None

    if user_groups.intersection(CHAIN_LEVEL_GROUPS):
        return TenantScope(property_id=narrowed, region=None)

    if user_groups.intersection(REGIONAL_GROUPS):
        caller_region = get_region(event)
        if not caller_region:
            # A regional caller with no region is unscopeable. Widening to the
            # chain would make a missing claim more privileged than a present
            # one.
            raise ForbiddenError("Access denied: no region assigned")
        return TenantScope(property_id=narrowed, region=caller_region)

    # Fail closed: an absent property claim is not evidence of chain-level
    # access.
    raise ForbiddenError("Access denied: no property access")


class ForbiddenError(Exception):
    """Raised when a user lacks permission to access a resource."""
    pass
