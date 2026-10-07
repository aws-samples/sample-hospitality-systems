"""
Outbound HTTPS for Lambda code.

urllib's default opener (``urlopen`` / ``build_opener``) also speaks ``file://``,
``ftp://``, ``data:`` and plain ``http://``. If a URL is ever influenced by
configuration or input, that default can read local files or send a bearer
token in cleartext. This module builds an opener that registers ONLY the HTTPS
handler, so any other scheme fails with ``URLError("unknown url type")`` by
construction, not by a string check that could be gotten wrong.

Two further restrictions apply:

- Hosts are allowlisted per call. A caller names the exact hosts it expects,
  and anything else is rejected before a connection is made.
- Redirects are not followed. Callers here talk to fixed AWS endpoints that
  don't redirect, and following one would let the remote side choose a
  different host. A 3xx surfaces as ``urllib.error.HTTPError``.

No proxy handler is registered; Lambda egress goes through the VPC's NAT
gateway and endpoints directly.
"""

import ssl
import urllib.parse
import urllib.request
from collections.abc import Collection


def _build_opener() -> urllib.request.OpenerDirector:
    opener = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        # Without this, an unhandled scheme makes open() quietly return None;
        # with it, any non-https scheme raises URLError("unknown url type").
        urllib.request.UnknownHandler(),
        # Turn non-2xx responses into HTTPError, the same as urlopen does.
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPErrorProcessor(),
    ):
        opener.add_handler(handler)
    return opener


_OPENER = _build_opener()


def host_of(url: str) -> str:
    """Return the lower-cased hostname of ``url`` (``""`` if it has none)."""
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def open_https(
    request: str | urllib.request.Request,
    *,
    allowed_hosts: Collection[str],
    timeout: float,
):
    """Open an HTTPS URL on an allowlisted host; return the response.

    Args:
        request: A URL string or a prepared ``urllib.request.Request``.
        allowed_hosts: Exact hostnames this call may reach (case-insensitive).
        timeout: Socket timeout in seconds.

    Returns:
        The response object (use as a context manager, as with ``urlopen``).

    Raises:
        ValueError: The URL isn't ``https://`` or its host isn't allowlisted.
        urllib.error.HTTPError: Non-2xx response, including any redirect.
        urllib.error.URLError: Connection failure.
    """
    url = request.full_url if isinstance(request, urllib.request.Request) else request
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise ValueError(f"Only https:// URLs are allowed, got {parts.scheme!r}")
    host = (parts.hostname or "").lower()
    if host not in {h.lower() for h in allowed_hosts}:
        raise ValueError(f"Host {host!r} is not in the allowlist")
    return _OPENER.open(request, timeout=timeout)
