"""
Shared engine for contract capture + verify.

Normalizes a response down to its *contract*: status code, response-body
structure (keys and value types), and the presence of required key paths —
deliberately discarding volatile values (ids, timestamps, prices, counts)
that legitimately differ run-to-run and between environments.

The captured baseline and each replay are compared on this normalized form.
A diff means the API contract changed.
"""

import json
import os
import urllib.error
import urllib.request

import boto3
from matrix import VOLATILE_KEYS
from utils.https import host_of, open_https

REGION = os.environ.get("AWS_REGION", "us-east-1")
STACK_NAME = os.environ.get("TEST_STACK_NAME", "anycompany-booking")
ENV = os.environ.get("TEST_ENV", "dev")
TESTSUITE_SECRET = f"anycompany-booking-testsuite-creds-{ENV}"


def _normalize(value):
    """Reduce a JSON value to its structural skeleton.

    - dict -> dict with same keys (volatile keys dropped), values normalized
    - list -> normalized type-skeleton of the FIRST element only (list length
      and element values are not part of the contract; element SHAPE is)
    - scalar -> a type token ("<str>", "<int>", "<float>", "<bool>", "<null>")

    This makes the snapshot stable across data changes while still catching
    structural drift (renamed/removed keys, changed types, list-vs-object).
    """
    if isinstance(value, dict):
        out = {}
        for k, v in sorted(value.items()):
            if k in VOLATILE_KEYS:
                continue
            out[k] = _normalize(v)
        return out
    if isinstance(value, list):
        if not value:
            return ["<empty>"]
        return [_normalize(value[0])]
    if isinstance(value, bool):
        return "<bool>"
    if isinstance(value, int):
        return "<int>"
    if isinstance(value, float):
        return "<float>"
    if value is None:
        return "<null>"
    return "<str>"


def normalize_response(status, body):
    """The contract record for one request: status + normalized body."""
    return {"status": status, "body": _normalize(body)}


def get_key_path(body, dotted):
    """Return True if a dotted key path exists in the (raw) body."""
    cur = body
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False
    return True


# ---- runtime context (stack outputs, tokens, placeholder ids) ----

class ContractContext:
    """Resolves stack outputs, mints tokens, and fills path placeholders."""

    def __init__(self):
        self.session = boto3.Session(region_name=REGION)
        cfn = self.session.client("cloudformation")
        outs = cfn.describe_stacks(StackName=STACK_NAME)["Stacks"][0]["Outputs"]
        self.outputs = {o["OutputKey"]: o["OutputValue"] for o in outs}
        # ApiUrl / PmsApiUrl are the CRS and PMS API base URLs (stack outputs).
        self.crs_base = self.outputs["ApiUrl"].rstrip("/")
        self.pms_base = self.outputs["PmsApiUrl"].rstrip("/")
        # Requests carry bearer tokens: allow only the stack's two API hosts.
        self.api_hosts = {host_of(self.crs_base), host_of(self.pms_base)}

        sm = self.session.client("secretsmanager")
        creds = json.loads(sm.get_secret_value(SecretId=TESTSUITE_SECRET)["SecretString"])
        self._password = creds["password"]
        self._users = creds["users"]
        self._pool = self.outputs["UserPoolId"]
        # Dedicated admin-auth client for ADMIN_USER_PASSWORD_AUTH (not the
        # public SPA client, which is SRP-only).
        self._client_id = self.outputs["AdminAuthClientId"]
        self._cognito = self.session.client("cognito-idp")
        self._token_cache = {}
        self._placeholders = None

    def token(self, role):
        if role in self._token_cache:
            return self._token_cache[role]
        email = self._users[role]["email"]
        resp = self._cognito.admin_initiate_auth(
            UserPoolId=self._pool, ClientId=self._client_id,
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": self._password},
        )
        tok = resp["AuthenticationResult"]["IdToken"]
        self._token_cache[role] = tok
        return tok

    def placeholders(self):
        """Resolve {propertyId}/{roomTypeId} from real data once."""
        if self._placeholders is not None:
            return self._placeholders
        rds = self.session.client("rds-data")
        resp = rds.execute_statement(
            resourceArn=self.outputs["DBClusterArn"],
            secretArn=self.outputs["DBSecretArn"],
            database="anycompany",
            includeResultMetadata=True,
            sql=(
                "SELECT rt.property_id, rt.room_type_id "
                "FROM room_types rt JOIN properties p ON p.property_id = rt.property_id "
                "WHERE p.is_active = true AND rt.is_active = true LIMIT 1"
            ),
        )
        rec = resp["records"][0]
        self._placeholders = {
            "propertyId": rec[0]["stringValue"],
            "roomTypeId": rec[1]["stringValue"],
        }
        return self._placeholders

    def resolve_path(self, path):
        ph = self.placeholders()
        for key, val in ph.items():
            path = path.replace("{" + key + "}", val)
        return path

    def call(self, entry):
        base = self.crs_base if entry["api"] == "crs" else self.pms_base
        path = self.resolve_path(entry["path"])
        url = base + path
        headers = {"Content-Type": "application/json"}
        if entry["role"]:
            headers["Authorization"] = f"Bearer {self.token(entry['role'])}"
        data = json.dumps(entry["body"]).encode() if entry.get("body") is not None else None
        req = urllib.request.Request(url, method=entry["method"], headers=headers, data=data)
        try:
            with open_https(req, allowed_hosts=self.api_hosts, timeout=30) as resp:
                return resp.status, json.loads(resp.read() or "null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or "null")
