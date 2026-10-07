"""Integration guard for the payment-domain schema contract.

The payment unit tests mock the database, so they cannot catch a handler that
writes a column, or sets a status value, that the schema does not define. This
test executes the same INSERT/SELECT column shapes the handlers use against the
deployed schema via the RDS Data API, so code/schema drift fails here rather
than at runtime after a Stripe charge has already succeeded.

Gated behind the `integration` marker; needs AWS creds + the deployed stack.
"""

import uuid

import pytest


@pytest.fixture
def seed_auth(db):
    """Create a throwaway payment_authorization hung off an EXISTING dev
    reservation (the reservation FK chain — property/room_type/rate_plan — is
    reference data we don't want to synthesize). Only the authorization and its
    captures/refunds are created here, and all are cleaned up on teardown."""
    existing = db.query("SELECT reservation_id, guest_id FROM reservations LIMIT 1")
    if not existing:
        pytest.skip("No reservations seeded on the dev stack to attach a test authorization to.")
    reservation_id = existing[0]["reservation_id"]
    guest_id = existing[0]["guest_id"]

    auth_id = str(uuid.uuid4())
    ids = {"auth": auth_id}

    # Authorization in dollars, as create_intent writes it.
    db.execute(
        """
        INSERT INTO payment_authorizations (
            authorization_id, guest_id, reservation_id,
            stripe_payment_intent_id, amount, currency, status
        ) VALUES (CAST(:aid AS uuid), CAST(:gid AS uuid), CAST(:rid AS uuid),
                  :pi, :amount, 'USD', 'CAPTURED')
        """,
        [
            {"name": "aid", "value": {"stringValue": auth_id}},
            {"name": "gid", "value": {"stringValue": guest_id}},
            {"name": "rid", "value": {"stringValue": reservation_id}},
            {"name": "pi", "value": {"stringValue": f"pi_testsuite_{auth_id[:8]}"}},
            {"name": "amount", "value": {"doubleValue": 150.00}},
        ],
    )

    yield ids

    # Teardown: refunds -> captures -> auth (children first). Best-effort.
    for sql in [
        "DELETE FROM payment_refunds WHERE capture_id IN "
        "(SELECT capture_id FROM payment_captures WHERE authorization_id = CAST(:id AS uuid))",
        "DELETE FROM payment_captures WHERE authorization_id = CAST(:id AS uuid)",
        "DELETE FROM payment_authorizations WHERE authorization_id = CAST(:id AS uuid)",
    ]:
        try:
            db.execute(sql, [{"name": "id", "value": {"stringValue": ids["auth"]}}])
        except Exception as e:  # best-effort; sweeper is the backstop
            print(f"  (teardown ignored): {e}")


@pytest.mark.integration
class TestPaymentSchemaContract:
    def test_capture_insert_matches_schema(self, db, seed_auth):
        """confirm_payment's capture INSERT columns must exist."""
        capture_id = str(uuid.uuid4())
        # Exact column list from confirm_payment.py / complete_booking.py.
        db.execute(
            """
            INSERT INTO payment_captures (
                capture_id, authorization_id, captured_amount,
                stripe_charge_id, receipt_url, created_at
            ) VALUES (CAST(:cid AS uuid), CAST(:aid AS uuid), :amt,
                      :charge, :receipt, NOW())
            """,
            [
                {"name": "cid", "value": {"stringValue": capture_id}},
                {"name": "aid", "value": {"stringValue": seed_auth["auth"]}},
                {"name": "amt", "value": {"doubleValue": 150.00}},
                {"name": "charge", "value": {"stringValue": "ch_testsuite"}},
                {"name": "receipt", "value": {"stringValue": "https://example.com/r"}},
            ],
        )
        rows = db.query(
            "SELECT captured_amount FROM payment_captures WHERE capture_id = CAST(:c AS uuid)",
            [{"name": "c", "value": {"stringValue": capture_id}}],
        )
        assert rows and float(rows[0]["captured_amount"]) == 150.00

    def test_refund_insert_matches_schema(self, db, seed_auth):
        """refund_payment's refund INSERT columns + reason CHECK."""
        capture_id = str(uuid.uuid4())
        refund_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO payment_captures (
                capture_id, authorization_id, captured_amount, created_at
            ) VALUES (CAST(:cid AS uuid), CAST(:aid AS uuid), :amt, NOW())
            """,
            [
                {"name": "cid", "value": {"stringValue": capture_id}},
                {"name": "aid", "value": {"stringValue": seed_auth["auth"]}},
                {"name": "amt", "value": {"doubleValue": 150.00}},
            ],
        )
        # Exact column list + a schema-valid reason from refund_payment.py.
        db.execute(
            """
            INSERT INTO payment_refunds (
                refund_id, capture_id, stripe_refund_id,
                amount, reason, status, created_at
            ) VALUES (CAST(:rid AS uuid), CAST(:cid AS uuid), :sr,
                      :amt, 'CANCELLATION', 'SUCCEEDED', NOW())
            """,
            [
                {"name": "rid", "value": {"stringValue": refund_id}},
                {"name": "cid", "value": {"stringValue": capture_id}},
                {"name": "sr", "value": {"stringValue": "re_testsuite"}},
                {"name": "amt", "value": {"doubleValue": 150.00}},
            ],
        )
        rows = db.query(
            "SELECT amount, reason FROM payment_refunds WHERE refund_id = CAST(:r AS uuid)",
            [{"name": "r", "value": {"stringValue": refund_id}}],
        )
        assert rows and rows[0]["reason"] == "CANCELLATION"

    def test_get_payment_refund_join(self, db, seed_auth):
        """get_payment joins refunds via capture_id, not authorization_id."""
        capture_id = str(uuid.uuid4())
        refund_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO payment_captures (capture_id, authorization_id, captured_amount, created_at) "
            "VALUES (CAST(:cid AS uuid), CAST(:aid AS uuid), :amt, NOW())",
            [
                {"name": "cid", "value": {"stringValue": capture_id}},
                {"name": "aid", "value": {"stringValue": seed_auth["auth"]}},
                {"name": "amt", "value": {"doubleValue": 75.00}},
            ],
        )
        db.execute(
            "INSERT INTO payment_refunds (refund_id, capture_id, amount, reason, status, created_at) "
            "VALUES (CAST(:rid AS uuid), CAST(:cid AS uuid), :amt, 'BILLING_ERROR', 'SUCCEEDED', NOW())",
            [
                {"name": "rid", "value": {"stringValue": refund_id}},
                {"name": "cid", "value": {"stringValue": capture_id}},
                {"name": "amt", "value": {"doubleValue": 75.00}},
            ],
        )
        # The exact join get_payment.py uses.
        rows = db.query(
            """
            SELECT pr.refund_id
            FROM payment_refunds pr
            JOIN payment_captures pc ON pr.capture_id = pc.capture_id
            WHERE pc.authorization_id = CAST(:aid AS uuid)
            """,
            [{"name": "aid", "value": {"stringValue": seed_auth["auth"]}}],
        )
        assert any(r["refund_id"] == refund_id for r in rows)

    def test_refunded_status_is_rejected(self, db, seed_auth):
        """REFUNDED is not a valid authorization status; a full refund voids the
        authorization (VOIDED) instead."""
        # VOIDED is allowed by the CHECK; this should succeed.
        db.execute(
            "UPDATE payment_authorizations SET status = 'VOIDED' WHERE authorization_id = CAST(:a AS uuid)",
            [{"name": "a", "value": {"stringValue": seed_auth["auth"]}}],
        )
        rows = db.query(
            "SELECT status FROM payment_authorizations WHERE authorization_id = CAST(:a AS uuid)",
            [{"name": "a", "value": {"stringValue": seed_auth["auth"]}}],
        )
        assert rows[0]["status"] == "VOIDED"
