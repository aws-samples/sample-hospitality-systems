"""
Shared pytest configuration for the backend test suite.

Responsibilities:
  1. Make handler packages importable. The shared layer (`utils.*`,
     `models.*`) is already on the path via pyproject.toml's `pythonpath`.
     Individual Lambda handlers live under per-domain CodeUri dirs and import
     each other by bare module name (e.g. night_audit's trigger.py does
     `from worker import handler`), mirroring how SAM packages each function.
     We add every CodeUri dir to sys.path so unit tests can import handlers
     the same way the Lambda runtime does.
  2. Provide env-var defaults so importing a handler module never blows up on
     a missing os.environ key at collection time.

No AWS clients or network calls happen here — unit tests are offline.
"""

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"


# ── Auto-mark tests by directory ─────────────────────────────────────────────
# Tests under tests/<layer>/ are automatically tagged with the matching marker,
# so individual files don't need to repeat @pytest.mark.<layer>. Keeps the
# default `-m unit` filter working without per-file boilerplate.
_DIR_MARKERS = {"unit", "integration", "contract", "e2e"}


def pytest_collection_modifyitems(config, items):
    for item in items:
        rel = Path(str(item.fspath)).relative_to(REPO_ROOT)
        # rel.parts == ("tests", "<layer>", ...)
        if len(rel.parts) >= 2 and rel.parts[0] == "tests":
            layer = rel.parts[1]
            if layer in _DIR_MARKERS:
                item.add_marker(getattr(pytest.mark, layer))

# ── 1. Handler import by explicit path ───────────────────────────────────────
# Handler files are NOT importable by bare module name in the test process,
# because several names collide across domains (list_properties exists in both
# property/ and pms/reporting/; process_event in billing/housekeeping/loyalty;
# sfn_actions in billing/housekeeping). At runtime SAM isolates each function in
# its own CodeUri so there's no collision — but a flat test sys.path would make
# `import list_properties` ambiguous. Instead, tests load a handler by its
# domain-qualified path via the `load_handler` fixture, which imports the file
# under a unique synthetic module name and puts the handler's own dir on
# sys.path first so its sibling imports (e.g. `from worker import handler`)
# still resolve.


def _load_handler(rel_path: str):
    """Import a handler module from its path relative to src/.

    Example: load_handler("property/list_properties.py").
    The module is registered under a unique name derived from the path, so
    same-named handlers in different domains never collide.
    """
    file_path = SRC / rel_path
    handler_dir = str(file_path.parent)
    # Ensure sibling-module imports within the handler's dir resolve.
    if handler_dir not in sys.path:
        sys.path.insert(0, handler_dir)
    mod_name = "handler_" + rel_path.replace("/", "_").replace(".py", "")
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


# ── 2. Safe env-var defaults for import-time and handler-level reads ─────────
# These are dummy values; unit tests mock the AWS calls that would use them.
# Real values are only needed by the integration/contract/e2e layers, which
# discover them from stack outputs in their own conftest.
_ENV_DEFAULTS = {
    "DB_PROXY_ENDPOINT": "test-proxy.local",
    "DB_NAME": "anycompany_test",
    "EVENT_BUS_NAME": "anycompany-events-test",
    "STRIPE_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:000000000000:secret:test-stripe",
    "COGNITO_USER_POOL_ID": "us-east-1_testpool",
    "ENVIRONMENT": "test",
    "AWS_REGION": "us-east-1",
    "AWS_DEFAULT_REGION": "us-east-1",
}


@pytest.fixture(autouse=True)
def _env_defaults(monkeypatch):
    """Ensure handler env-var reads resolve to harmless test values."""
    for key, value in _ENV_DEFAULTS.items():
        monkeypatch.setenv(key, value)


# ── Shared helpers available to all unit tests ──────────────────────────────
@pytest.fixture
def make_event():
    """
    Build a mock API Gateway event with JWT claims.

    Produces the Cognito user pool authorizer shape — claims live at
    requestContext.authorizer.claims, matching what the handlers read via
    utils.auth.get_claims.
    """
    def _build(
        body=None,
        path_params=None,
        query_params=None,
        property_id=None,
        region=None,
        groups=None,
        sub="user-123",
    ):
        claims = {"sub": sub}
        if property_id:
            claims["custom:property_id"] = property_id
        if region:
            claims["custom:region"] = region
        if groups is not None:
            claims["cognito:groups"] = groups

        event = {
            "requestContext": {"authorizer": {"claims": claims}},
            "pathParameters": path_params,
            "queryStringParameters": query_params,
        }
        if body is not None:
            import json
            event["body"] = body if isinstance(body, str) else json.dumps(body)
        return event

    return _build


class _LambdaContext:
    """Minimal stand-in for the AWS Lambda context object.

    aws_lambda_powertools' @logger.inject_lambda_context reads these
    attributes; passing None (as a bare unit test might) raises
    AttributeError. Handlers decorated with inject_lambda_context should be
    invoked with this object as the second arg.
    """
    function_name = "test-fn"
    memory_limit_in_mb = 256
    invoked_function_arn = "arn:aws:lambda:us-east-1:000000000000:function:test-fn"
    aws_request_id = "test-request-id"


@pytest.fixture
def lambda_context():
    """A mock Lambda context for handlers using inject_lambda_context."""
    return _LambdaContext()


@pytest.fixture
def load_handler():
    """Return the path-based handler loader (see _load_handler)."""
    return _load_handler


@pytest.fixture
def mock_db():
    """
    Build a mock psycopg connection whose cursors return scripted rows.

    Handlers use the pattern:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(...); cur.fetchone()/fetchall()

    Each `with conn.cursor()` block gets the *next* scripted result in order,
    so a handler that opens N cursor blocks needs N queued results. Queue a
    result with `.queue(fetchone=..., fetchall=...)`.

    Returns an object with `.conn` (pass to your get_conn patch) and helpers.
    """
    class _MockDB:
        def __init__(self):
            self.conn = MagicMock()
            self.conn.closed = False
            self._results = []
            self._idx = 0
            # Each entry/exit of conn.cursor() yields the next scripted cursor.
            self.conn.cursor.side_effect = self._next_cursor
            # Support handlers that use `with get_conn() as conn:` — the
            # connection acts as its own context manager.
            self.conn.__enter__ = MagicMock(return_value=self.conn)
            self.conn.__exit__ = MagicMock(return_value=False)

        def queue(self, fetchone=None, fetchall=None):
            self._results.append({"fetchone": fetchone, "fetchall": fetchall or []})
            return self

        def _next_cursor(self, *args, **kwargs):
            # Cursors are used as context managers: `with conn.cursor() as cur`.
            if self._idx < len(self._results):
                spec = self._results[self._idx]
            else:
                spec = {"fetchone": None, "fetchall": []}
            self._idx += 1

            cur = MagicMock()
            cur.fetchone.return_value = spec["fetchone"]
            cur.fetchall.return_value = spec["fetchall"]
            cur.description = ["col"]
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=cur)
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

    return _MockDB()
