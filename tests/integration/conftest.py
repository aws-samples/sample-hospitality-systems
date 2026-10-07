"""
Integration-layer fixtures: run against the REAL dev stack.

These tests need AWS credentials (set `AWS_PROFILE` to your profile; region
us-east-1) and the seeded test users (run
`python scripts/seed_test_users.py` once). They are gated behind the
`integration` marker and never run in the default `make test-unit` loop.

Provides:
  - stack_outputs:   CloudFormation outputs (API URLs, DB ARNs, pool IDs)
  - db:              RDS Data API helper (query/execute against the cluster)
  - token_for:       mint a Cognito ID token for a given test role
  - api / pms_api:   thin authenticated request clients for each API
  - track:           register a testsuite- record for guaranteed teardown

All created data uses the `testsuite-` marker and is cleaned up on
teardown; tests/sweeper.py is the backstop for orphans.
"""

import json
import os
import time
import urllib.error
import urllib.request

import boto3
import pytest
from utils.https import host_of, open_https

STACK_NAME = os.environ.get("TEST_STACK_NAME", "anycompany-booking")
REGION = os.environ.get("AWS_REGION", "us-east-1")
ENV = os.environ.get("TEST_ENV", "dev")
TESTSUITE_SECRET = f"anycompany-booking-testsuite-creds-{ENV}"


@pytest.fixture(scope="session")
def aws():
    """Session-scoped boto3 session honoring AWS_PROFILE / AWS_REGION."""
    return boto3.Session(region_name=REGION)


@pytest.fixture(scope="session")
def stack_outputs(aws):
    cfn = aws.client("cloudformation")
    outs = cfn.describe_stacks(StackName=STACK_NAME)["Stacks"][0]["Outputs"]
    return {o["OutputKey"]: o["OutputValue"] for o in outs}


@pytest.fixture(scope="session")
def test_creds(aws):
    """The seeded test-user roster + shared password from Secrets Manager."""
    sm = aws.client("secretsmanager")
    try:
        raw = sm.get_secret_value(SecretId=TESTSUITE_SECRET)["SecretString"]
    except sm.exceptions.ResourceNotFoundException:
        pytest.skip(
            f"Test-user secret {TESTSUITE_SECRET} not found — run "
            "scripts/seed_test_users.py first."
        )
    return json.loads(raw)


@pytest.fixture(scope="session")
def db(aws, stack_outputs):
    """RDS Data API helper bound to the dev cluster."""
    rds_data = aws.client("rds-data")
    cluster_arn = stack_outputs["DBClusterArn"]
    secret_arn = stack_outputs["DBSecretArn"]

    class _DB:
        def execute(self, sql, params=None, include_metadata=False):
            kwargs = {
                "resourceArn": cluster_arn,
                "secretArn": secret_arn,
                "database": "anycompany",
                "sql": sql,
            }
            if params:
                kwargs["parameters"] = params
            if include_metadata:
                kwargs["includeResultMetadata"] = True
            return rds_data.execute_statement(**kwargs)

        def query(self, sql, params=None):
            """Return rows as a list of dicts (column name -> scalar)."""
            resp = self.execute(sql, params, include_metadata=True)
            cols = [c["name"] for c in resp.get("columnMetadata", [])]
            rows = []
            for record in resp.get("records", []):
                row = {}
                for col, field in zip(cols, record, strict=True):
                    row[col] = next(
                        (v for k, v in field.items() if k != "isNull"), None
                    ) if not field.get("isNull") else None
                rows.append(row)
            return rows

    return _DB()


@pytest.fixture(scope="session")
def token_for(aws, stack_outputs, test_creds):
    """Factory: token_for('admin') -> a Cognito ID token for that role.

    Uses AdminInitiateAuth (the same flow the simulator uses) against the
    dedicated admin-auth client (AdminAuthClientId), not the public SPA client
    — the SPA client is SRP-only.
    """
    cognito = aws.client("cognito-idp")
    pool_id = stack_outputs["UserPoolId"]
    client_id = stack_outputs["AdminAuthClientId"]
    password = test_creds["password"]
    cache = {}

    def _get(role):
        if role in cache:
            return cache[role]
        email = test_creds["users"][role]["email"]
        resp = cognito.admin_initiate_auth(
            UserPoolId=pool_id,
            ClientId=client_id,
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": password},
        )
        token = resp["AuthenticationResult"]["IdToken"]
        cache[role] = token
        return token

    return _get


def _request(method, url, allowed_hosts, token=None, body=None):
    """Call a stack API over HTTPS. Requests carry bearer tokens, so only the
    calling client's own API host is allowed (see utils.https)."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    try:
        with open_https(req, allowed_hosts=allowed_hosts, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


@pytest.fixture
def api(stack_outputs, token_for):
    """Authenticated client for the CRS API. api.get(path, role=...)."""
    base = stack_outputs["ApiUrl"].rstrip("/")
    hosts = {host_of(base)}

    class _Client:
        def _call(self, method, path, role=None, body=None):
            token = token_for(role) if role else None
            return _request(method, base + path, hosts, token, body)

        def get(self, path, role=None):
            return self._call("GET", path, role)

        def post(self, path, body=None, role=None):
            return self._call("POST", path, role, body)

        def put(self, path, body=None, role=None):
            return self._call("PUT", path, role, body)

        def delete(self, path, role=None):
            return self._call("DELETE", path, role)

    return _Client()


@pytest.fixture
def pms_api(stack_outputs, token_for):
    """Authenticated client for the PMS API."""
    base = stack_outputs["PmsApiUrl"].rstrip("/")
    hosts = {host_of(base)}

    class _Client:
        def _call(self, method, path, role=None, body=None):
            token = token_for(role) if role else None
            return _request(method, base + path, hosts, token, body)

        def get(self, path, role=None):
            return self._call("GET", path, role)

        def post(self, path, body=None, role=None):
            return self._call("POST", path, role, body)

        def put(self, path, body=None, role=None):
            return self._call("PUT", path, role, body)

        def delete(self, path, role=None):
            return self._call("DELETE", path, role)

    return _Client()


@pytest.fixture
def track(db):
    """Register testsuite- records for guaranteed teardown.

    Usage:
        track.guest(guest_id)
        track.reservation(reservation_id)
    On teardown, deletes the tracked rows (children first). The sweeper is
    the backstop for anything a crashed run leaves behind.
    """
    created = {"reservation": [], "guest": []}

    class _Track:
        def reservation(self, rid):
            created["reservation"].append(rid)

        def guest(self, gid):
            created["guest"].append(gid)

    yield _Track()

    # Teardown: children before parents. Best-effort; never raise.
    for rid in created["reservation"]:
        try:
            db.execute("DELETE FROM reservations WHERE reservation_id = CAST(:id AS uuid)",
                       [{"name": "id", "value": {"stringValue": rid}}])
        except Exception as e:
            print(f"  (teardown ignored) reservation {rid}: {e}")
    for gid in created["guest"]:
        try:
            db.execute("DELETE FROM guests WHERE guest_id = CAST(:id AS uuid)",
                       [{"name": "id", "value": {"stringValue": gid}}])
        except Exception as e:
            print(f"  (teardown ignored) guest {gid}: {e}")
