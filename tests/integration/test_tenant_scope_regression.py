"""Integration regression tests: PMS tenant scope cannot be widened by the caller.

Live counterpart to tests/unit/test_tenant_fail_closed.py, run against the
deployed dev stack.

Three properties are pinned here:

1. Cognito config: `custom:property_id` / `custom:region` must not be
   client-writable. They are authorization inputs, so a signed-in user who
   could edit them could re-scope themselves.
2. Handler scoping fails closed: a staff user whose scope can't be
   established (no property claim, no chain-level group) is denied, not
   handed every property. This is proven with the deliberately mis-provisioned
   `testsuite-frontdesk-unscoped` user.
3. Handler scoping: a caller can narrow their scope but never widen or move
   it. A property-pinned caller's `?propertyId=` is ignored, and a regional
   caller can't reach outside their region by naming a property.

These tests read data and never create it. The one Cognito write
(`test_self_service_write_of_property_claim_is_rejected`) writes the attribute's
CURRENT value, so even if a regression lets it succeed it changes nothing.
"""

from datetime import date, timedelta

import pytest
from botocore.exceptions import ClientError

SCOPE_ATTRIBUTES = {"custom:property_id", "custom:region"}


# ── helpers ──────────────────────────────────────────────────────────────────

def _str(params):
    return [{"name": k, "value": {"stringValue": v}} for k, v in params.items()]


@pytest.fixture(scope="module")
def own_property(test_creds):
    """The property the testsuite FrontDesk / Housekeeping users are pinned to."""
    return test_creds["property_id"]


@pytest.fixture(scope="module")
def other_property(db, own_property):
    """Some other active property: the one a caller must NOT be able to reach."""
    rows = db.query(
        "SELECT property_id::text AS property_id FROM properties "
        "WHERE is_active = TRUE AND property_id <> CAST(:own AS uuid) "
        "ORDER BY property_id LIMIT 1",
        _str({"own": own_property}),
    )
    if not rows:
        pytest.skip("Need at least two active properties on the dev stack.")
    return rows[0]["property_id"]


def _total(body):
    return body["data"]["pagination"]["total"]


# ── 1. Cognito client configuration ──────────────────────────────────────────

class TestScopeAttributesAreNotSelfService:
    @pytest.mark.parametrize("output_key", ["UserPoolClientId", "AdminAuthClientId"])
    def test_client_cannot_write_scope_attributes(self, aws, stack_outputs, output_key):
        client = aws.client("cognito-idp").describe_user_pool_client(
            UserPoolId=stack_outputs["UserPoolId"],
            ClientId=stack_outputs[output_key],
        )["UserPoolClient"]
        writable = set(client.get("WriteAttributes", []))
        assert not writable & SCOPE_ATTRIBUTES, (
            f"{client['ClientName']} lets signed-in users write "
            f"{sorted(writable & SCOPE_ATTRIBUTES)}"
        )

    @pytest.mark.parametrize("output_key", ["UserPoolClientId", "AdminAuthClientId"])
    def test_client_still_reads_scope_attributes(self, aws, stack_outputs, output_key):
        """The claims must still reach the token, or scoped staff break."""
        client = aws.client("cognito-idp").describe_user_pool_client(
            UserPoolId=stack_outputs["UserPoolId"],
            ClientId=stack_outputs[output_key],
        )["UserPoolClient"]
        assert set(client.get("ReadAttributes", [])) >= SCOPE_ATTRIBUTES

    def test_self_service_write_of_property_claim_is_rejected(
        self, aws, stack_outputs, test_creds
    ):
        cognito = aws.client("cognito-idp")
        pool_id = stack_outputs["UserPoolId"]
        email = test_creds["users"]["frontdesk"]["email"]

        def current_value():
            attrs = cognito.admin_get_user(UserPoolId=pool_id, Username=email)
            return {a["Name"]: a["Value"] for a in attrs["UserAttributes"]}.get(
                "custom:property_id"
            )

        before = current_value()
        assert before, "testsuite-frontdesk must be property-scoped"

        access_token = cognito.admin_initiate_auth(
            UserPoolId=pool_id,
            ClientId=stack_outputs["AdminAuthClientId"],
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": test_creds["password"]},
        )["AuthenticationResult"]["AccessToken"]

        try:
            with pytest.raises(ClientError) as exc:
                cognito.update_user_attributes(
                    AccessToken=access_token,
                    UserAttributes=[{"Name": "custom:property_id", "Value": before}],
                )
            assert exc.value.response["Error"]["Code"] == "NotAuthorizedException"
        finally:
            assert current_value() == before, "scope attribute must be unchanged"


# ── 2. A staff user with no scope is denied, not handed the chain ────────────

UNSCOPED_ROLE = "frontdesk_unscoped"


class TestUnscopedStaffIsDenied:
    """
    `testsuite-frontdesk-unscoped` is a FrontDesk user with NO
    `custom:property_id`: deliberately mis-provisioned. A collection handler
    that read the missing claim as "no filter" would return every property's
    data. Each of these endpoints admits FrontDesk, so a 403 here comes from the
    scope check, not the group gate.
    """

    @pytest.fixture(scope="class", autouse=True)
    def _unscoped_user_is_really_unscoped(self, test_creds, token_for):
        if UNSCOPED_ROLE not in test_creds["users"]:
            pytest.skip(
                f"{UNSCOPED_ROLE} not seeded; re-run scripts/seed_test_users.py"
            )
        import base64
        import json
        payload = token_for(UNSCOPED_ROLE).split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        # Preconditions, so the test can't pass for the wrong reason.
        assert not claims.get("custom:property_id"), "unscoped user has a property claim"
        assert not claims.get("custom:region"), "unscoped user has a region claim"
        assert "FrontDesk" in claims.get("cognito:groups", []), "unscoped user lost FrontDesk"

    @pytest.mark.parametrize("path", [
        "/stays?limit=1",
        "/billing/folios?limit=1",
        "/housekeeping/rooms/summary",
        "/properties",
    ])
    def test_collection_endpoint_denies_unscoped_staff(self, pms_api, path):
        status, body = pms_api.get(path, role=UNSCOPED_ROLE)
        total = ((body or {}).get("data") or {}).get("pagination", {}).get("total")
        assert status == 403, (
            f"unscoped FrontDesk got {status} on {path}"
            + (f" with {total} rows" if total is not None else "")
        )

    def test_unscoped_staff_cannot_name_a_property(self, pms_api, other_property):
        status, _ = pms_api.get(
            f"/stays?limit=1&propertyId={other_property}", role=UNSCOPED_ROLE
        )
        assert status == 403


# ── 3. Property-pinned callers cannot move ───────────────────────────────────

class TestPropertyPinnedCallerCannotMove:
    @pytest.mark.parametrize("role,path,rows_key", [
        ("frontdesk", "/stays", "stays"),
        ("housekeeping", "/housekeeping/tasks", "tasks"),
    ])
    def test_requested_property_is_ignored(
        self, pms_api, own_property, other_property, role, path, rows_key
    ):
        status, body = pms_api.get(f"{path}?limit=100&propertyId={other_property}", role=role)
        assert status == 200, body
        seen = {r["propertyId"] for r in body["data"][rows_key]}
        assert seen <= {own_property}, f"{role} reached {seen - {own_property}}"

    def test_folios_requested_property_is_ignored(self, pms_api, other_property):
        # Folio list items carry no propertyId, so compare result sets: naming
        # another property must return exactly the caller's own folios.
        s1, own = pms_api.get("/billing/folios?limit=1", role="frontdesk")
        s2, moved = pms_api.get(
            f"/billing/folios?limit=1&propertyId={other_property}", role="frontdesk"
        )
        assert (s1, s2) == (200, 200)
        assert _total(moved) == _total(own)


# ── 4. Regional callers cannot leave their region ────────────────────────────

class TestRegionalCallerCannotLeaveRegion:
    @pytest.fixture(scope="class")
    def outside_property_with_revenue(self, db, test_creds):
        """A property outside the regional user's region that has recent
        ROOM_RATE revenue, so an empty result can't pass vacuously."""
        rows = db.query(
            "SELECT f.property_id::text AS property_id "
            "FROM charges c JOIN folios f ON f.folio_id = c.folio_id "
            "JOIN properties p ON p.property_id = f.property_id "
            "WHERE p.is_active AND p.region IS DISTINCT FROM :region "
            "AND c.charge_type = 'ROOM_RATE' AND c.status = 'ACTIVE' "
            "AND c.charge_date >= CURRENT_DATE - 29 "
            "GROUP BY f.property_id ORDER BY SUM(c.amount) DESC LIMIT 1",
            _str({"region": test_creds["region"]}),
        )
        if not rows:
            pytest.skip("No out-of-region property with recent revenue.")
        return rows[0]["property_id"]

    def test_range_report_for_out_of_region_property_is_empty(
        self, pms_api, outside_property_with_revenue
    ):
        end = date.today()
        start = end - timedelta(days=29)
        path = (
            f"/reporting/range?propertyId={outside_property_with_revenue}"
            f"&startDate={start}&endDate={end}"
        )

        # Precondition: the property really has revenue (seen chain-wide).
        status, admin = pms_api.get(path, role="admin")
        assert status == 200, admin
        assert admin["data"]["totals"]["revenue"] > 0

        status, regional = pms_api.get(path, role="regional")
        assert status == 200, regional
        totals = regional["data"]["totals"]
        assert totals["revenue"] == 0 and totals["roomNightsSold"] == 0, (
            "regional caller read an out-of-region property's revenue"
        )

    def test_property_list_stays_within_region(self, pms_api, test_creds):
        status, body = pms_api.get("/properties", role="regional")
        assert status == 200, body
        regions = {p.get("region") for p in body["data"]["properties"]}
        assert regions <= {test_creds["region"]}
