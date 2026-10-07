"""Integration guard for the cart-completion availability race.

complete_booking claims inventory with a capacity-guarded, atomic UPDATE:

    UPDATE availability SET sold = sold + 1
    WHERE room_type_id = :rt AND date >= :ci AND date < :co
      AND (total_inventory - sold - blocked) + COALESCE(overbooking_allowance, 0) > 0

and aborts if fewer rows than nights are updated. This test exercises that
exact statement against the real schema (availability.available is a GENERATED
column) to prove the last unit can only be claimed once — a second concurrent
claim updates zero rows.

Gated behind the `integration` marker; needs AWS creds + the deployed stack.
"""

import uuid

import pytest


# The exact capacity-guarded claim used by complete_booking Step F.
CLAIM_SQL = """
    UPDATE availability SET sold = sold + 1
    WHERE room_type_id = CAST(:rt AS uuid)
      AND date >= CAST(:ci AS date) AND date < CAST(:co AS date)
      AND (total_inventory - sold - blocked) + COALESCE(overbooking_allowance, 0) > 0
"""


@pytest.fixture
def last_unit_availability(db):
    """Seed a single availability row for a throwaway room_type with exactly
    one sellable unit (total_inventory=1, sold=0, overbooking=0), hung off an
    existing property. Cleaned up on teardown."""
    prop = db.query("SELECT property_id FROM properties LIMIT 1")
    if not prop:
        pytest.skip("No properties on the dev stack.")
    property_id = prop[0]["property_id"]

    # A room_type FK is required by availability; reuse an existing one for
    # this property if present, else skip (don't synthesize reference data).
    rt = db.query(
        "SELECT room_type_id FROM room_types WHERE property_id = CAST(:p AS uuid) LIMIT 1",
        [{"name": "p", "value": {"stringValue": property_id}}],
    )
    if not rt:
        pytest.skip("No room_types for the chosen property.")
    room_type_id = rt[0]["room_type_id"]

    # Use a date far in the future to avoid colliding with real/seeded inventory.
    the_date = "2099-12-31"
    # Remove any pre-existing row for this (room_type, date) then insert ours.
    db.execute(
        "DELETE FROM availability WHERE room_type_id = CAST(:rt AS uuid) AND date = CAST(:d AS date)",
        [{"name": "rt", "value": {"stringValue": room_type_id}},
         {"name": "d", "value": {"stringValue": the_date}}],
    )
    db.execute(
        """
        INSERT INTO availability (room_type_id, date, property_id,
                                  total_inventory, sold, blocked, overbooking_allowance)
        VALUES (CAST(:rt AS uuid), CAST(:d AS date), CAST(:p AS uuid), 1, 0, 0, 0)
        """,
        [{"name": "rt", "value": {"stringValue": room_type_id}},
         {"name": "d", "value": {"stringValue": the_date}},
         {"name": "p", "value": {"stringValue": property_id}}],
    )

    yield {"room_type_id": room_type_id, "date": the_date}

    db.execute(
        "DELETE FROM availability WHERE room_type_id = CAST(:rt AS uuid) AND date = CAST(:d AS date)",
        [{"name": "rt", "value": {"stringValue": room_type_id}},
         {"name": "d", "value": {"stringValue": the_date}}],
    )


@pytest.mark.integration
class TestAvailabilityClaim:
    def test_last_unit_claimed_only_once(self, db, last_unit_availability):
        rt = last_unit_availability["room_type_id"]
        d = last_unit_availability["date"]
        # date < co means we cover exactly the single night [d, d+1).
        ci, co = d, "2100-01-01"
        params = [
            {"name": "rt", "value": {"stringValue": rt}},
            {"name": "ci", "value": {"stringValue": ci}},
            {"name": "co", "value": {"stringValue": co}},
        ]

        # First claim: takes the only unit.
        r1 = db.execute(CLAIM_SQL, params)
        assert r1["numberOfRecordsUpdated"] == 1

        # available is now 0 (generated: 1 - 1 - 0). Second claim must be a no-op.
        r2 = db.execute(CLAIM_SQL, params)
        assert r2["numberOfRecordsUpdated"] == 0, (
            "capacity guard failed — the last unit was claimed twice (overbooking)"
        )

        # Confirm the generated column reflects a single sale.
        rows = db.query(
            "SELECT sold, available FROM availability "
            "WHERE room_type_id = CAST(:rt AS uuid) AND date = CAST(:d AS date)",
            [{"name": "rt", "value": {"stringValue": rt}},
             {"name": "d", "value": {"stringValue": d}}],
        )
        assert rows[0]["sold"] == 1 and rows[0]["available"] == 0

    def test_overbooking_allowance_permits_one_more(self, db, last_unit_availability):
        """With overbooking_allowance=1, the guard should allow exactly one
        claim beyond total_inventory, then stop."""
        rt = last_unit_availability["room_type_id"]
        d = last_unit_availability["date"]
        db.execute(
            "UPDATE availability SET overbooking_allowance = 1 "
            "WHERE room_type_id = CAST(:rt AS uuid) AND date = CAST(:d AS date)",
            [{"name": "rt", "value": {"stringValue": rt}},
             {"name": "d", "value": {"stringValue": d}}],
        )
        params = [
            {"name": "rt", "value": {"stringValue": rt}},
            {"name": "ci", "value": {"stringValue": d}},
            {"name": "co", "value": {"stringValue": "2100-01-01"}},
        ]
        # unit 1 (available=1), unit 2 (available=0 but overbooking=1) both allowed.
        assert db.execute(CLAIM_SQL, params)["numberOfRecordsUpdated"] == 1
        assert db.execute(CLAIM_SQL, params)["numberOfRecordsUpdated"] == 1
        # third claim: available=-1, +overbooking 1 = 0 → blocked.
        assert db.execute(CLAIM_SQL, params)["numberOfRecordsUpdated"] == 0
