"""
Seed dedicated test users for the integration/contract/E2E test suite.

Provisions one Cognito user per role so tests can exercise real
authorization and tenant-isolation paths (not just happy-path-as-Admin),
and stores their shared password in Secrets Manager so the test harness can
authenticate without hardcoded credentials.

Users (all email-prefixed `testsuite-` so the sweeper and any audit can
distinguish them from demo/simulator/real data):

    testsuite-admin@example.test         Admin           chain-level
    testsuite-manager@example.test       Manager         chain-level
    testsuite-regional@example.test      RegionalManager region-scoped
    testsuite-frontdesk@example.test     FrontDesk       property-pinned
    testsuite-housekeeping@example.test  Housekeeping    property-pinned
    testsuite-guest@example.test         (none)          guest-facing CRS

Usage:
    python scripts/seed_test_users.py \\
        --user-pool-id <your-user-pool-id> \\
        --profile <your-profile> \\
        --region us-east-1 \\
        --property-id <a-seeded-property-id>

Idempotent: existing users are left in place (password reset to the known
value so the secret stays authoritative). Safe to re-run.

The credentials secret is named `anycompany-booking-testsuite-creds-<env>`.
"""

import argparse
import json
import secrets
import string

import boto3

EMAIL_DOMAIN = "example.test"

# role-name -> (email local part, cognito groups, scope)
TEST_USERS = [
    ("admin",        "testsuite-admin",        ["Admin"],            "chain"),
    ("manager",      "testsuite-manager",      ["Manager"],          "chain"),
    ("regional",     "testsuite-regional",     ["RegionalManager"],  "region"),
    ("frontdesk",    "testsuite-frontdesk",    ["FrontDesk"],        "property"),
    ("housekeeping", "testsuite-housekeeping", ["Housekeeping"],     "property"),
    ("guest",        "testsuite-guest",        [],                   "guest"),
]


def _gen_password() -> str:
    """Generate a strong password meeting the Cognito policy (upper/lower/
    digit; symbols not required by this pool)."""
    alphabet = string.ascii_letters + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(20))
    # Guarantee policy compliance regardless of random draw.
    return "Tt1" + body


def upsert_user(cognito, pool_id, email, groups, scope, password, property_id, region):
    attributes = [
        {"Name": "email", "Value": email},
        {"Name": "email_verified", "Value": "true"},
        {"Name": "given_name", "Value": "Test"},
        {"Name": "family_name", "Value": email.split("@")[0]},
    ]
    if scope == "property" and property_id:
        attributes.append({"Name": "custom:property_id", "Value": property_id})
    if scope == "region" and region:
        attributes.append({"Name": "custom:region", "Value": region})

    try:
        cognito.admin_create_user(
            UserPoolId=pool_id,
            Username=email,
            UserAttributes=attributes,
            TemporaryPassword=password,
            MessageAction="SUPPRESS",
        )
        print(f"  created {email}")
    except cognito.exceptions.UsernameExistsException:
        print(f"  exists  {email} (resetting password + attributes)")
        cognito.admin_update_user_attributes(
            UserPoolId=pool_id, Username=email, UserAttributes=attributes
        )

    cognito.admin_set_user_password(
        UserPoolId=pool_id, Username=email, Password=password, Permanent=True
    )

    for group in groups:
        cognito.admin_add_user_to_group(
            UserPoolId=pool_id, Username=email, GroupName=group
        )
    if groups:
        print(f"          groups: {', '.join(groups)}")


def main():
    parser = argparse.ArgumentParser(description="Seed integration-test users")
    parser.add_argument("--user-pool-id", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--profile")
    parser.add_argument("--property-id", required=True,
                        help="Real active property_id to scope property/region users to")
    parser.add_argument("--scope-region", default="Northeast",
                        help="Region value for the regional test user")
    parser.add_argument("--env", default="dev")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cognito = session.client("cognito-idp")
    secretsmgr = session.client("secretsmanager")

    print(f"\nSeeding test users into pool {args.user_pool_id}\n")

    password = _gen_password()
    creds = {}

    for role, local, groups, scope in TEST_USERS:
        email = f"{local}@{EMAIL_DOMAIN}"
        upsert_user(
            cognito, args.user_pool_id, email, groups, scope,
            password, args.property_id, args.scope_region,
        )
        creds[role] = {"email": email, "groups": groups, "scope": scope}

    # Store the shared password + the per-role roster in one secret.
    secret_name = f"anycompany-booking-testsuite-creds-{args.env}"
    secret_value = json.dumps({
        "password": password,
        "property_id": args.property_id,
        "region": args.scope_region,
        "users": creds,
    })
    try:
        secretsmgr.create_secret(Name=secret_name, SecretString=secret_value)
        print(f"\n  created secret {secret_name}")
    except secretsmgr.exceptions.ResourceExistsException:
        secretsmgr.put_secret_value(SecretId=secret_name, SecretString=secret_value)
        print(f"\n  updated secret {secret_name}")

    print(f"\nDone. {len(TEST_USERS)} test users ready; creds in {secret_name}.")


if __name__ == "__main__":
    main()
