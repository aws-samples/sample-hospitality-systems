"""
Auth utilities for AnyCompany Hotel platform.

Extracts JWT claims from the API Gateway authorizer context and provides
helpers for ownership verification and role-based access control. The APIs
use a Cognito user pool authorizer, which places the verified token claims
at event["requestContext"]["authorizer"]["claims"].
"""

from typing import Any


def get_claims(event: dict) -> dict[str, Any]:
    """
    Extract JWT claims from the API Gateway request event.

    The Cognito user pool authorizer places claims at
    event["requestContext"]["authorizer"]["claims"].

    Args:
        event: Lambda event from API Gateway.

    Returns:
        Dict of JWT claims.

    Raises:
        KeyError: If the authorizer context is missing from the event.
        ForbiddenError: If a raw bearer token is present on the event and its
            signature/claims fail re-verification (defense in depth). When no
            raw token is present we fall back to the
            authorizer-provided claims, which the API Gateway Cognito authorizer
            has already validated in the request path.
    """
    # Defense-in-depth: if the raw JWT is on the event, re-verify its signature
    # against the user pool JWKS before trusting any claims. No-op when absent
    # or when disabled via JWT_VERIFY_ENABLED=false.
    from utils.jwt_verify import verify_event_token
    verify_event_token(event)

    authorizer = event.get("requestContext", {}).get("authorizer", {})

    if "claims" in authorizer:
        return authorizer["claims"]

    # Fallback: authorizer context is the claims dict itself
    return authorizer


def get_guest_id(event: dict) -> str:
    """
    Extract the guest ID (sub claim) from the JWT token.

    The 'sub' claim is expected to contain the guest's unique identifier
    (UUID) as issued by the Auth Service.

    Args:
        event: Lambda event from API Gateway.

    Returns:
        Guest ID string from the JWT 'sub' claim.
    """
    claims = get_claims(event)
    return claims["sub"]


def get_email(event: dict) -> str | None:
    """
    Extract the email from the JWT token, if present.

    Args:
        event: Lambda event from API Gateway.

    Returns:
        Email string or None if not present in claims.
    """
    claims = get_claims(event)
    return claims.get("email")


def get_roles(event: dict) -> list[str]:
    """
    Extract roles from the JWT token.

    Roles are expected as a space-separated string in the 'scope' claim
    or as a custom 'roles' claim containing a comma-separated list.

    Args:
        event: Lambda event from API Gateway.

    Returns:
        List of role strings.
    """
    claims = get_claims(event)
    roles_claim = claims.get("roles", "")
    if isinstance(roles_claim, list):
        return roles_claim
    return [r.strip() for r in roles_claim.split(",") if r.strip()]


def require_owner(event: dict, resource_guest_id: str) -> dict | None:
    """
    Verify that the authenticated user owns the requested resource.

    Compares the JWT 'sub' claim against the provided resource_guest_id.
    Returns an error response dict if they do not match, or None if
    ownership is confirmed.

    Args:
        event: Lambda event from API Gateway.
        resource_guest_id: The guest ID that owns the resource.

    Returns:
        None if the caller owns the resource, or a 403 error response dict.
    """
    caller_id = get_guest_id(event)
    if caller_id != resource_guest_id:
        # Re-import to avoid a circular dependency at module load time.
        from utils.response import forbidden
        return forbidden()
    return None


def get_groups(event: dict) -> list[str]:
    """
    Extract Cognito groups from the JWT claims.

    Groups appear in the 'cognito:groups' claim. The claim can arrive in a
    few shapes depending on how the value is serialized, so handle all of them:
    - a JSON list: ["Admin", "Manager"]
    - a bracketed, space-separated string: "[Admin Manager]"
      (API Gateway serializes a multi-valued claim this way)
    - a comma-separated string: "Admin,Manager"
    """
    claims = get_claims(event)
    groups = claims.get("cognito:groups", "")
    if isinstance(groups, list):
        return groups
    if isinstance(groups, str) and groups:
        cleaned = groups.strip("[]")
        if not cleaned:
            return []
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
    user_groups = set(get_groups(event))
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
        from utils.tenant import ForbiddenError
        raise ForbiddenError("Access denied: insufficient permissions")


def get_region(event: dict) -> str | None:
    """
    Extract the region from the JWT custom:region claim.

    Used for RegionalManager access scoping.

    Args:
        event: Lambda event from API Gateway.

    Returns:
        Region string or None if not present.
    """
    claims = get_claims(event)
    return claims.get("custom:region") or None


def get_user_id(event: dict) -> str:
    """
    Extract the user ID (sub claim) from the JWT token.

    Args:
        event: Lambda event from API Gateway.

    Returns:
        User ID string from the JWT 'sub' claim.
    """
    claims = get_claims(event)
    return claims["sub"]
