"""
Sweeper: delete all `testsuite-` data from the dev stack.

The integration tests create data marked with the `testsuite-` prefix
(guest emails like testsuite-<uuid>@example.test). Fixtures clean up on
teardown, but a hard crash can orphan rows. This script is the backstop:
run it any time via `make sweep` to remove every testsuite- record.

SAFETY: this only ever targets guests whose email starts with
`testsuite-`, then cascades to that guest's children. It NEVER touches
`simguest-` (simulator) or demo/real data. Every DELETE is scoped to the
set of testsuite guest_ids; if that set is empty, nothing is deleted.

It does NOT delete the seeded Cognito test users or their credentials
secret — those are durable fixtures provisioned by seed_test_users.py.
Re-running the seed script is how you reset those.

Usage:
    AWS_PROFILE=<your-profile> AWS_REGION=us-east-1 python tests/sweeper.py
    # or: make sweep
"""

import os
import sys

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
STACK_NAME = os.environ.get("TEST_STACK_NAME", "anycompany-booking")
PREFIX = "testsuite-"

# Child tables to clear (in FK-safe order) before deleting the guests
# themselves. Each entry: (table, the column that ties it to a guest, or a
# subquery via reservations/folios).
#
# We resolve the set of testsuite guest_ids once, plus their reservation_ids
# and folio_ids, then delete from the leaves inward.


def _client():
    session = boto3.Session(region_name=REGION)
    cfn = session.client("cloudformation")
    outs = {o["OutputKey"]: o["OutputValue"]
            for o in cfn.describe_stacks(StackName=STACK_NAME)["Stacks"][0]["Outputs"]}
    return session.client("rds-data"), outs["DBClusterArn"], outs["DBSecretArn"]


def main():
    rds_data, cluster_arn, secret_arn = _client()

    # All statements are static SQL. The only variable is the testsuite prefix,
    # bound as the named parameter :like (no SQL is built from strings).
    like_param = [{"name": "like", "value": {"stringValue": PREFIX + "%"}}]

    def execute(sql, params=None):
        return rds_data.execute_statement(
            resourceArn=cluster_arn, secretArn=secret_arn,
            database="anycompany", sql=sql, parameters=params or [],
        )

    def scalars(sql, params=None):
        resp = execute(sql, params)
        out = []
        for rec in resp.get("records", []):
            field = rec[0]
            if not field.get("isNull"):
                out.append(next(v for k, v in field.items() if k != "isNull"))
        return out

    guest_ids = scalars(
        "SELECT guest_id FROM guests WHERE email LIKE :like", like_param
    )
    if not guest_ids:
        print("No testsuite- guests found. Nothing to sweep.")
        return 0

    print(f"Found {len(guest_ids)} testsuite- guests. Sweeping their data...")

    # Delete order matters for FK constraints. payment_captures references
    # payment_authorizations, so captures must go first. Leaves -> parents:
    #   captures -> authorizations -> payments -> charges -> folios
    #   -> reservation children -> reservations -> guest children -> guests
    #
    # Every statement is a fully static string literal; the only variable is the
    # testsuite prefix, bound as :like. The repeated
    # "guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like)" subquery
    # is written inline (not composed from f-strings) so it stays static.
    statements = [
        # Captures can be tied to a testsuite folio OR authorization; scope by
        # both so a partially-swept run still clears them (folios may already
        # be gone while their captures' authorizations remain).
        "DELETE FROM payment_captures "
        "WHERE folio_id IN (SELECT folio_id FROM folios "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like)) "
        "OR authorization_id IN (SELECT authorization_id FROM payment_authorizations "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like))",
        "DELETE FROM payment_authorizations "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like)",
        "DELETE FROM payments "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like)",
        "DELETE FROM charges "
        "WHERE folio_id IN (SELECT folio_id FROM folios "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like))",
        "DELETE FROM folios "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like)",
        "DELETE FROM housekeeping_tasks "
        "WHERE reservation_id IN (SELECT reservation_id FROM reservations "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like))",
        "DELETE FROM reservation_services "
        "WHERE reservation_id IN (SELECT reservation_id FROM reservations "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like))",
        "DELETE FROM checkinout_records "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like)",
        "DELETE FROM loyalty_transactions "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like)",
        "DELETE FROM reservations "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like)",
        "DELETE FROM booking_carts "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like)",
        "DELETE FROM stored_payment_methods "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like)",
        "DELETE FROM guest_identity_documents "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like)",
        "DELETE FROM vouchers "
        "WHERE guest_id IN (SELECT guest_id FROM guests WHERE email LIKE :like)",
        # Finally the guests themselves.
        "DELETE FROM guests WHERE email LIKE :like",
    ]

    for sql in statements:
        table = sql.split("FROM ")[1].split(" ")[0]
        try:
            resp = execute(sql, like_param)
            n = resp.get("numberOfRecordsUpdated", 0)
            if n:
                print(f"  deleted {n:>5} from {table}")
        except Exception as e:
            print(f"  WARN  {table}: {e}")

    print("Sweep complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
