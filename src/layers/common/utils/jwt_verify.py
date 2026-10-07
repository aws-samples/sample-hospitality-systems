"""
JWT signature re-verification for defense in depth.

In the normal request path the API Gateway Cognito user-pool authorizer has
already validated the token before a handler runs, and the verified claims are
placed at ``event.requestContext.authorizer.claims``. That is the trusted source
for in-path requests.

This module adds a *second* layer: when the raw bearer token is present on the
event (``Authorization: Bearer <token>``), we re-verify its signature against the
user pool's JWKS and re-check the standard claims (expiry, token_use, audience,
issuer) inside the Lambda itself. This protects against any future invocation
path that is NOT fronted by the API Gateway authorizer (an EventBridge rule, an
internal caller, a console invoke) handing a handler forged claims.

Design (per the agreed approach — defense-in-depth, env-gated, fail-open-to-authorizer):
- If no raw token is present on the event, we do nothing and the caller falls
  back to the authorizer-provided claims (today's behavior). Event shapes that
  only carry the authorizer context (some tests, internal flows) keep working.
- If a raw token IS present and verification FAILS, we raise ForbiddenError —
  handlers already translate that to a clean 403.
- Verification can be disabled with JWT_VERIFY_ENABLED=false (e.g. for local
  unit tests that build synthetic events). It defaults to enabled.

The JWKS is fetched once per warm container over HTTPS (stdlib urllib via
utils.https, so no extra dependency) and cached in a module global with a TTL,
so the steady-state cost is the signature check only (~0.06 ms/call measured);
the network fetch is paid once per container, not per request.
"""

import json
import os
import time
from typing import Any

import jwt
from jwt import PyJWTError
from jwt.algorithms import RSAAlgorithm

from utils.https import open_https

# JWKS cache (per warm container).
_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SECONDS = 3600  # Cognito signing keys are long-lived; refresh hourly.

_REGION = os.environ.get("AWS_REGION", "us-east-1")


def _verify_enabled() -> bool:
    return os.environ.get("JWT_VERIFY_ENABLED", "true").lower() != "false"


def _jwks_url() -> str:
    pool_id = os.environ["COGNITO_USER_POOL_ID"]
    return (
        f"https://cognito-idp.{_REGION}.amazonaws.com/"
        f"{pool_id}/.well-known/jwks.json"
    )


def _get_jwks(force_refresh: bool = False) -> dict:
    """Return the user pool's JWKS, cached for a TTL in a module global."""
    global _jwks_cache, _jwks_fetched_at

    now = time.monotonic()
    if (
        not force_refresh
        and _jwks_cache is not None
        and (now - _jwks_fetched_at) < _JWKS_TTL_SECONDS
    ):
        return _jwks_cache

    # The only host the JWKS may come from. Compared against the URL's parsed
    # hostname, so an unexpected AWS_REGION value that changes how the URL
    # parses is refused rather than fetched. open_https also enforces https://
    # and does not follow redirects.
    with open_https(
        _jwks_url(),
        allowed_hosts={f"cognito-idp.{_REGION}.amazonaws.com"},
        timeout=5,
    ) as resp:
        _jwks_cache = json.loads(resp.read())
    _jwks_fetched_at = now
    return _jwks_cache


def extract_bearer_token(event: dict) -> str | None:
    """Pull the raw JWT from the Authorization header, if present.

    API Gateway may lower-case header keys, so check both. Returns None when no
    bearer token is on the event (the fall-back-to-authorizer case).
    """
    headers = event.get("headers") or {}
    auth = headers.get("Authorization") or headers.get("authorization")
    if not auth:
        return None
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def verify_token(token: str) -> dict[str, Any]:
    """Verify a Cognito ID token's signature + standard claims; return its claims.

    Raises PyJWTError on any failure (bad signature, expired, wrong audience/issuer,
    unknown key, malformed token).
    """
    pool_id = os.environ["COGNITO_USER_POOL_ID"]
    issuer = f"https://cognito-idp.{_REGION}.amazonaws.com/{pool_id}"

    # Match the signing key by kid; refresh the JWKS once if the kid is unknown
    # (covers a key rotation that happened after our cache was populated).
    kid = jwt.get_unverified_header(token).get("kid")

    def _key_for(jwks):
        return next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)

    jwk = _key_for(_get_jwks())
    if jwk is None:
        jwk = _key_for(_get_jwks(force_refresh=True))
    if jwk is None:
        raise PyJWTError(f"No matching JWKS key for kid={kid}")

    signing_key = RSAAlgorithm.from_jwk(json.dumps(jwk))

    # The SPA + admin clients are the only audiences that mint ID tokens used
    # here. PyJWT verifies the audience natively against a list (any-match), and
    # enforces issuer + expiry. Pass our client-id allowlist as the audience.
    allowed_audiences = [
        v
        for v in (
            os.environ.get("COGNITO_USER_POOL_CLIENT_ID"),
            os.environ.get("ADMIN_AUTH_CLIENT_ID"),
        )
        if v
    ]

    claims = jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        issuer=issuer,
        audience=allowed_audiences if allowed_audiences else None,
        options={
            "require": ["exp"],
            "verify_aud": bool(allowed_audiences),
        },
    )

    # Cognito ID tokens carry token_use == "id". Reject access tokens.
    if claims.get("token_use") not in (None, "id"):
        raise PyJWTError(f"Unexpected token_use: {claims.get('token_use')}")

    return claims


def verify_event_token(event: dict) -> None:
    """Defense-in-depth check called from get_claims().

    - Disabled via JWT_VERIFY_ENABLED=false → no-op.
    - No raw bearer token on the event → no-op (fall back to authorizer claims).
    - Raw token present but invalid → raise ForbiddenError (handlers → 403).
    """
    if not _verify_enabled():
        return

    token = extract_bearer_token(event)
    if token is None:
        return

    try:
        verify_token(token)
    except (PyJWTError, KeyError, ValueError) as e:
        # Re-imported here to avoid a circular import at module load.
        from utils.tenant import ForbiddenError

        raise ForbiddenError(f"Token verification failed: {e}") from e
