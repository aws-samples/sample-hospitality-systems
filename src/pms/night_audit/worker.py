"""
PMS Night Audit Worker.

Scheduled Lambda (cron: 11:59 PM ET daily) or manual trigger.
Posts room charges to in-house guest folios and generates daily metrics.
"""

import json
import os
import uuid
from datetime import date, datetime

from utils.database import get_conn
from utils.events import publish_event
from utils.logger import get_logger

logger = get_logger("pms-night-audit")

TAX_RATE = float(os.environ.get("TAX_RATE", "0.15"))


@logger.inject_lambda_context
def handler(event, context):
    """Run night audit for all active properties."""
    # Determine audit date (today or from event)
    audit_date_str = event.get("auditDate") or str(date.today())
    audit_date = datetime.strptime(audit_date_str, "%Y-%m-%d").date()
    triggered_by = event.get("triggeredBy", "schedule")

    logger.info("Starting night audit", audit_date=audit_date_str, triggered_by=triggered_by)

    properties_processed = 0
    total_charges_posted = 0

    with get_conn() as conn, conn.cursor() as cur:
        # Get all active properties
        cur.execute("SELECT property_id, name FROM properties WHERE is_active = true")
        properties = cur.fetchall()

        for prop in properties:
            property_id = prop["property_id"]
            result = _process_property(cur, property_id, audit_date, triggered_by)
            properties_processed += 1
            total_charges_posted += result.get("charges_posted", 0)

        conn.commit()

    # Publish completion event (best-effort)
    try:
        publish_event(
            source="anycompany.audit",
            detail_type="audit.night_completed",
            detail={
                "auditDate": audit_date_str,
                "propertiesProcessed": properties_processed,
                "totalChargesPosted": total_charges_posted,
                "triggeredBy": triggered_by,
            },
        )
    except Exception:
        logger.exception("Failed to publish audit.night_completed event")

    logger.info("Night audit complete",
               properties=properties_processed, charges=total_charges_posted)

    return {
        "auditDate": audit_date_str,
        "propertiesProcessed": properties_processed,
        "totalChargesPosted": total_charges_posted,
    }


def _process_property(cur, property_id, audit_date, triggered_by):
    """Process night audit for a single property."""
    charges_posted = 0

    # Find all in-house guests (CHECKED_IN reservations)
    cur.execute(
        "SELECT r.reservation_id, r.guest_id, r.room_type_id, r.check_in_date, "
        "r.check_out_date, f.folio_id "
        "FROM reservations r "
        "JOIN folios f ON r.reservation_id = f.reservation_id AND f.status = 'OPEN' "
        "WHERE r.property_id = %s AND r.status = 'CHECKED_IN'",
        [property_id],
    )
    in_house = cur.fetchall()

    for stay in in_house:
        # Check if room charge already posted for this date (idempotency)
        cur.execute(
            "SELECT charge_id FROM charges "
            "WHERE folio_id = %s AND charge_type = 'ROOM_RATE' AND charge_date = %s "
            "AND status = 'ACTIVE'",
            [stay["folio_id"], audit_date],
        )
        if cur.fetchone():
            continue  # Already posted for today

        # Get nightly rate (from existing room rate charges as reference)
        cur.execute(
            "SELECT amount FROM charges "
            "WHERE folio_id = %s AND charge_type = 'ROOM_RATE' AND status = 'ACTIVE' "
            "ORDER BY charge_date DESC LIMIT 1",
            [stay["folio_id"]],
        )
        rate_row = cur.fetchone()
        nightly_rate = float(rate_row["amount"]) if rate_row else 0

        if nightly_rate > 0:
            charge_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO charges "
                "(charge_id, folio_id, charge_type, description, amount, charge_date) "
                "VALUES (%s, %s, 'ROOM_RATE', %s, %s, %s)",
                [charge_id, stay["folio_id"],
                 f"Room charge - {audit_date.strftime('%b %d')}",
                 nightly_rate, audit_date],
            )
            charges_posted += 1

    # Calculate daily metrics
    cur.execute(
        "SELECT COUNT(*) as total_rooms FROM rooms WHERE property_id = %s",
        [property_id],
    )
    total_rooms = cur.fetchone()["total_rooms"]

    cur.execute(
        "SELECT COUNT(*) as occupied FROM rooms WHERE property_id = %s AND status = 'OCCUPIED'",
        [property_id],
    )
    occupied = cur.fetchone()["occupied"]

    occupancy_pct = round((occupied / total_rooms * 100), 1) if total_rooms > 0 else 0

    # Revenue for the day
    cur.execute(
        "SELECT COALESCE(SUM(c.amount), 0) as revenue "
        "FROM charges c JOIN folios f ON c.folio_id = f.folio_id "
        "WHERE f.property_id = %s AND c.charge_date = %s "
        "AND c.status = 'ACTIVE' AND c.charge_type = 'ROOM_RATE'",
        [property_id, audit_date],
    )
    daily_revenue = float(cur.fetchone()["revenue"])

    metrics = {
        "totalRooms": total_rooms,
        "occupiedRooms": occupied,
        "occupancyPercent": occupancy_pct,
        "roomsSold": len(in_house),
        "dailyRevenue": daily_revenue,
        "chargesPosted": charges_posted,
        "adr": round(daily_revenue / occupied, 2) if occupied > 0 else 0,
    }

    # Upsert audit run (idempotent)
    run_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO night_audit_runs (run_id, audit_date, property_id, metrics, triggered_by) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (audit_date, property_id) DO UPDATE SET "
        "metrics = EXCLUDED.metrics, triggered_by = EXCLUDED.triggered_by",
        [run_id, audit_date, property_id, json.dumps(metrics), triggered_by],
    )

    return {"charges_posted": charges_posted, "metrics": metrics}
