"""Unit tests for utils.https: the HTTPS-only, host-allowlisted opener.

No network is used. Every rejection below must happen before a connection is
attempted, and the opener's handler set is asserted directly.
"""

import urllib.error
import urllib.request

import pytest
from utils import https

ALLOWED = {"api.example.com"}


class TestRejectedBeforeConnecting:
    @pytest.mark.parametrize("url", [
        "file:///etc/passwd",
        "http://api.example.com/x",
        "ftp://api.example.com/x",
        "data:text/plain,hello",
    ])
    def test_non_https_scheme(self, url):
        with pytest.raises(ValueError, match="https"):
            https.open_https(url, allowed_hosts=ALLOWED, timeout=1)

    @pytest.mark.parametrize("url", [
        "https://evil.example.net/x",
        "https://api.example.com.evil.net/x",      # suffix trick
        "https://api.example.com@evil.net/x",      # userinfo trick
        "https://evil.net#@api.example.com/x",     # fragment trick
    ])
    def test_host_not_allowlisted(self, url):
        with pytest.raises(ValueError, match="allowlist"):
            https.open_https(url, allowed_hosts=ALLOWED, timeout=1)

    def test_request_object_is_checked_too(self):
        req = urllib.request.Request("http://api.example.com/x")
        with pytest.raises(ValueError, match="https"):
            https.open_https(req, allowed_hosts=ALLOWED, timeout=1)

    def test_host_match_is_case_insensitive(self, monkeypatch):
        opened = []
        monkeypatch.setattr(https._OPENER, "open", lambda r, timeout: opened.append(r))
        https.open_https("https://API.Example.COM/x", allowed_hosts=ALLOWED, timeout=1)
        assert opened == ["https://API.Example.COM/x"]


class TestOpenerHandlers:
    """The opener itself can't speak anything but HTTPS, and doesn't redirect."""

    def _handler_types(self):
        return {type(h) for h in https._OPENER.handlers}

    def test_only_https_transport(self):
        types = self._handler_types()
        assert urllib.request.HTTPSHandler in types
        for unwanted in (
            urllib.request.HTTPHandler,
            urllib.request.FileHandler,
            urllib.request.FTPHandler,
            urllib.request.DataHandler,
            urllib.request.ProxyHandler,
        ):
            assert unwanted not in types

    def test_redirects_are_not_followed(self):
        assert urllib.request.HTTPRedirectHandler not in self._handler_types()

    def test_file_scheme_unsupported_by_construction(self):
        """Even bypassing open_https's checks, the opener can't read files."""
        with pytest.raises(urllib.error.URLError, match="unknown url type"):
            https._OPENER.open("file:///etc/passwd", timeout=1)


def test_host_of():
    assert https.host_of("https://API.example.com:443/p?q=1") == "api.example.com"
    assert https.host_of("not a url") == ""
