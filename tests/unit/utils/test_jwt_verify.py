"""Unit tests for defense-in-depth JWT signature re-verification.

Covers the verify_token / verify_event_token contract:
- a validly signed Cognito-style ID token passes,
- a token signed by a DIFFERENT key (forged) is rejected,
- an expired token is rejected,
- a wrong-audience / wrong-issuer / access-token is rejected,
- an unknown kid triggers a single JWKS refresh,
- get_claims() falls open to authorizer claims when no raw token is present,
- get_claims() raises ForbiddenError when a present token fails verification,
- JWT_VERIFY_ENABLED=false disables the check.

The JWKS network fetch (urllib) is monkeypatched; no network is used.
"""

import base64
import importlib
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWTError

POOL_ID = "us-east-1_TESTPOOL"
REGION = "us-east-1"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"
CLIENT_ID = "spaclient123"
KID = "testkid-1"


def _b64u(n: int) -> str:
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _make_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _priv_pem(key):
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _jwk(key, kid=KID):
    nums = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64u(nums.n),
        "e": _b64u(nums.e),
    }


def _token(key, *, kid=KID, aud=CLIENT_ID, iss=ISSUER, token_use="id", exp_delta=3600,
           extra=None):
    claims = {
        "sub": "user-uuid-1",
        "cognito:groups": ["Admin"],
        "email": "admin@anycompanyhotels.com",
        "aud": aud,
        "iss": iss,
        "token_use": token_use,
        "exp": int(time.time()) + exp_delta,
        "iat": int(time.time()),
    }
    if extra:
        claims.update(extra)
    return jwt.encode(claims, _priv_pem(key), algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def jv(monkeypatch):
    """Import the module fresh with env set, and stub the JWKS fetch."""
    monkeypatch.setenv("AWS_REGION", REGION)
    monkeypatch.setenv("COGNITO_USER_POOL_ID", POOL_ID)
    monkeypatch.setenv("COGNITO_USER_POOL_CLIENT_ID", CLIENT_ID)
    monkeypatch.delenv("ADMIN_AUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("JWT_VERIFY_ENABLED", raising=False)

    import utils.jwt_verify as m
    importlib.reload(m)

    # Reset cache between tests.
    m._jwks_cache = None
    m._jwks_fetched_at = 0.0
    return m


def _install_jwks(monkeypatch, jv_module, jwks_keys, counter=None, calls=None):
    """Patch _get_jwks indirectly by stubbing the HTTPS fetch to return the JWKS.

    `calls`, if given, collects (url, allowed_hosts) for each fetch.
    """
    payload = json.dumps({"keys": jwks_keys}).encode()

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            if counter is not None:
                counter.append(1)
            return payload

    def _fake_open_https(url, *, allowed_hosts, timeout):
        if calls is not None:
            calls.append((url, set(allowed_hosts)))
        return _Resp()

    monkeypatch.setattr(jv_module, "open_https", _fake_open_https)


def test_valid_token_passes(jv, monkeypatch):
    key = _make_key()
    _install_jwks(monkeypatch, jv, [_jwk(key)])
    claims = jv.verify_token(_token(key))
    assert claims["sub"] == "user-uuid-1"
    assert claims["email"] == "admin@anycompanyhotels.com"


def test_jwks_fetched_only_from_the_cognito_host(jv, monkeypatch):
    """The JWKS fetch is pinned to the exact Cognito host for the region."""
    key = _make_key()
    calls = []
    _install_jwks(monkeypatch, jv, [_jwk(key)], calls=calls)
    jv.verify_token(_token(key))
    url, allowed = calls[0]
    assert url == f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}/.well-known/jwks.json"
    assert allowed == {f"cognito-idp.{REGION}.amazonaws.com"}


def test_forged_signature_rejected(jv, monkeypatch):
    real, attacker = _make_key(), _make_key()
    # JWKS publishes the REAL key; token is signed by the ATTACKER key (same kid).
    _install_jwks(monkeypatch, jv, [_jwk(real)])
    with pytest.raises(PyJWTError):
        jv.verify_token(_token(attacker))


def test_expired_token_rejected(jv, monkeypatch):
    key = _make_key()
    _install_jwks(monkeypatch, jv, [_jwk(key)])
    with pytest.raises(PyJWTError):
        jv.verify_token(_token(key, exp_delta=-10))


def test_wrong_audience_rejected(jv, monkeypatch):
    key = _make_key()
    _install_jwks(monkeypatch, jv, [_jwk(key)])
    with pytest.raises(PyJWTError):
        jv.verify_token(_token(key, aud="someone-elses-client"))


def test_wrong_issuer_rejected(jv, monkeypatch):
    key = _make_key()
    _install_jwks(monkeypatch, jv, [_jwk(key)])
    with pytest.raises(PyJWTError):
        jv.verify_token(_token(key, iss="https://evil.example.com"))


def test_access_token_rejected(jv, monkeypatch):
    key = _make_key()
    _install_jwks(monkeypatch, jv, [_jwk(key)])
    with pytest.raises(PyJWTError):
        jv.verify_token(_token(key, token_use="access"))


def test_unknown_kid_triggers_single_refresh(jv, monkeypatch):
    key = _make_key()
    calls = []
    # JWKS returns a key with a DIFFERENT kid than the token's header.
    _install_jwks(monkeypatch, jv, [_jwk(key, kid="other-kid")], counter=calls)
    with pytest.raises(PyJWTError):
        jv.verify_token(_token(key, kid="missing-kid"))
    # Should have fetched twice: initial + one forced refresh on unknown kid.
    assert len(calls) == 2


def test_admin_audience_accepted(jv, monkeypatch):
    monkeypatch.setenv("ADMIN_AUTH_CLIENT_ID", "adminclient456")
    importlib.reload(jv)
    jv._jwks_cache = None
    jv._jwks_fetched_at = 0.0
    key = _make_key()
    _install_jwks(monkeypatch, jv, [_jwk(key)])
    claims = jv.verify_token(_token(key, aud="adminclient456"))
    assert claims["aud"] == "adminclient456"


# --- extract_bearer_token ---

def test_extract_bearer_present(jv):
    evt = {"headers": {"Authorization": "Bearer abc.def.ghi"}}
    assert jv.extract_bearer_token(evt) == "abc.def.ghi"


def test_extract_bearer_lowercased(jv):
    evt = {"headers": {"authorization": "Bearer xyz"}}
    assert jv.extract_bearer_token(evt) == "xyz"


def test_extract_bearer_absent(jv):
    assert jv.extract_bearer_token({"headers": {}}) is None
    assert jv.extract_bearer_token({}) is None


def test_extract_bearer_malformed(jv):
    assert jv.extract_bearer_token({"headers": {"Authorization": "Basic xyz"}}) is None


# --- verify_event_token (the get_claims integration point) ---

def test_event_no_token_is_noop(jv, monkeypatch):
    # No Authorization header → fall open, no exception even with a bad JWKS.
    jv.verify_event_token({"requestContext": {"authorizer": {"claims": {"sub": "u"}}}})


def test_event_valid_token_passes(jv, monkeypatch):
    key = _make_key()
    _install_jwks(monkeypatch, jv, [_jwk(key)])
    evt = {"headers": {"Authorization": f"Bearer {_token(key)}"}}
    jv.verify_event_token(evt)  # no raise


def test_event_invalid_token_raises_forbidden(jv, monkeypatch):
    real, attacker = _make_key(), _make_key()
    _install_jwks(monkeypatch, jv, [_jwk(real)])
    from utils.tenant import ForbiddenError

    evt = {"headers": {"Authorization": f"Bearer {_token(attacker)}"}}
    with pytest.raises(ForbiddenError):
        jv.verify_event_token(evt)


def test_disabled_flag_skips_verification(jv, monkeypatch):
    monkeypatch.setenv("JWT_VERIFY_ENABLED", "false")
    # Even a clearly bogus token must be ignored when disabled.
    evt = {"headers": {"Authorization": "Bearer not.a.real.token"}}
    jv.verify_event_token(evt)  # no raise
