"""
PMS Activity Simulator.

Scheduled Lambda (every 4 hours) that drives realistic end-to-end hotel activity
across both the CRS booking flow and the PMS staff operations. The simulator
authenticates as a dedicated `simulator@anycompanyhotels.local` Cognito user in
the Admin group; bookings are attributed to a pre-seeded pool of dedicated
simguest- profiles (sized by scripts/seed_simulator_guests.py) via an
operate-as-guest override on the booking endpoint.

Phases (in order, ordering is load-bearing):
1. check_out_guests          — POST /stays/{id}/checkout
2. process_housekeeping       — assign + complete + inspect (~85% pass / ~15% fail)
3. check_in_guests            — POST /stays/{id}/checkin (walks to another room on
                                 NO_ROOM_AVAILABLE so a saturated type doesn't lapse)
4. cancel_no_shows            — DELETE /reservations/{id} for stays whose window is
                                 fully past and were never checked in (no-shows)
5. add_incidental_charges     — POST /folios/{id}/charges (chargeType=SERVICE)
6. remove_charges             — POST /folios/{id}/charges (chargeType=ADJUSTMENT, negative)
7. create_reservations        — CRS booking flow with pi_simulated_<hex> sentinel
8. cancel_reservations        — DELETE /reservations/{id} with Admin bypass

Guest selection in create_reservations:
- Tier-weighted random pick (DIAMOND:GOLD:SILVER:NONE = 4:3:2:1) so loyalty
  activity reflects the seeded tier distribution.
- Skips guests who already hold a CONFIRMED/CHECKED_IN reservation overlapping
  the proposed window. Up to 10 weighted draws per slot before giving up;
  giving up increments the phase's "skip" count and emits an
  `overlap_skips` log line at phase end.
- The active-windows map is loaded fresh per run from the DB and updated
  in-memory as new reservations are booked, so within-run double-booking
  is also prevented.
"""

import json
import os
import random
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any

import boto3
from utils.https import host_of, open_https
from utils.logger import get_logger

logger = get_logger("pms-activity-simulator")

# ────────────────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────────────────

CRS_API_URL = os.environ["CRS_API_URL"]
PMS_API_URL = os.environ["PMS_API_URL"]
# The only hosts the simulator may call. Every request carries a bearer token,
# so outbound calls are limited to these hosts over HTTPS (see utils.https).
_ALLOWED_API_HOSTS = frozenset({host_of(CRS_API_URL), host_of(PMS_API_URL)})
COGNITO_USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
# Dedicated admin-auth client (not the public SPA client).
ADMIN_AUTH_CLIENT_ID = os.environ["ADMIN_AUTH_CLIENT_ID"]
SIMULATOR_CREDS_SECRET_ARN = os.environ["SIMULATOR_CREDS_SECRET_ARN"]

API_PACING_SECONDS = int(os.environ.get("API_PACING_MS", "50")) / 1000.0
MAX_RESERVATIONS_PER_RUN = int(os.environ.get("MAX_RESERVATIONS_PER_RUN", "30"))
# Per-run cap on check-ins. Set well above MAX_RESERVATIONS_PER_RUN so the phase
# can drain a backlog of due reservations faster than new ones mature, instead
# of only ever processing a single page.
MAX_CHECKINS_PER_RUN = int(os.environ.get("MAX_CHECKINS_PER_RUN", "150"))
# Per-run cap on check-OUTS. Must track MAX_CHECKINS_PER_RUN: every check-in
# eventually becomes a checkout, so if checkouts lag, occupied rooms never free
# up and later check-ins get blocked. Paginated (the /stays API caps a single
# page at 100), so this can exceed 100.
MAX_CHECKOUTS_PER_RUN = int(os.environ.get("MAX_CHECKOUTS_PER_RUN", "100"))
# Per-run cap on housekeeping tasks processed per status (assign+complete for
# PENDING/CLEANING, inspect for INSPECTING). Set above the checkout rate so
# vacated rooms are cleaned back to AVAILABLE before the next wave of arrivals.
# Paginated (the tasks API caps a single page at 100), so this can exceed 100.
MAX_HOUSEKEEPING_TASKS_PER_RUN = int(os.environ.get("MAX_HOUSEKEEPING_TASKS_PER_RUN", "100"))
MAX_INCIDENTAL_CHARGES_PER_RUN = int(os.environ.get("MAX_INCIDENTAL_CHARGES_PER_RUN", "15"))
MAX_CANCELLATIONS_PER_RUN = int(os.environ.get("MAX_CANCELLATIONS_PER_RUN", "5"))
# Per-run cap on no-show cancellations. Set high so the phase can drain a backlog
# of lapsed reservations rather than letting it grow run over run.
MAX_NO_SHOW_CANCELS_PER_RUN = int(os.environ.get("MAX_NO_SHOW_CANCELS_PER_RUN", "100"))
# How far ahead of today the simulator will book. Wider window = more
# distinct nights to land on, which raises the saturation ceiling for the
# overlap-avoidance retry loop in _phase_create_reservations.
FORWARD_WINDOW_DAYS = int(os.environ.get("FORWARD_WINDOW_DAYS", "30"))
# How many properties to request per booking search. The simulator picks one at
# random from this candidate set, so it must span (most of) the ~50 properties.
# /booking/search sorts is_featured DESC, price ASC and returns one row per
# property; a small limit (e.g. 5) funnels every booking into the same handful
# of featured hotels — saturating them while the rest sit at zero. Keep this at
# or above the property count so selection spreads across all available hotels.
SEARCH_CANDIDATE_LIMIT = int(os.environ.get("SEARCH_CANDIDATE_LIMIT", "50"))

INSPECTION_FAIL_RATE = 0.15
TOKEN_REFRESH_BUFFER_SECONDS = 120

# Incidental charge categories — descriptions only; chargeType is always SERVICE.
INCIDENTAL_DESCRIPTIONS = ["Room Service", "Spa", "Parking", "Minibar", "Laundry"]
HOUSEKEEPER_NAMES = [
    "Maria S.", "Carlos R.", "Aisha K.", "Diego M.", "Yuki T.",
    "Anna P.", "Raj S.", "Linh N.", "Omar A.", "Sofia L.",
]

# ────────────────────────────────────────────────────────────────────────────
# Module-level caches (warm-Lambda reuse)
# ────────────────────────────────────────────────────────────────────────────

_COGNITO_CLIENT = None
_SECRETS_CLIENT = None

_TOKEN: str | None = None
_TOKEN_EXPIRES_AT: float = 0.0
_CREDS: dict | None = None

_GUEST_POOL: list[tuple[str, str]] | None = None

# Tier weights for booking-frequency bias. DIAMOND members book ~4× more often
# than NONE; gives the activity feed a realistic loyalty mix without changing
# the underlying tier distribution in the seed.
TIER_WEIGHTS = {"DIAMOND": 4, "GOLD": 3, "SILVER": 2, "NONE": 1}
_PROPERTIES: list[dict] | None = None


def _cognito():
    global _COGNITO_CLIENT
    if _COGNITO_CLIENT is None:
        _COGNITO_CLIENT = boto3.client("cognito-idp")
    return _COGNITO_CLIENT


def _secrets():
    global _SECRETS_CLIENT
    if _SECRETS_CLIENT is None:
        _SECRETS_CLIENT = boto3.client("secretsmanager")
    return _SECRETS_CLIENT


# ────────────────────────────────────────────────────────────────────────────
# Auth — three refresh mechanisms (proactive, force, reactive)
# ────────────────────────────────────────────────────────────────────────────


def _load_creds() -> dict:
    """Load and cache simulator-user credentials from Secrets Manager."""
    global _CREDS
    if _CREDS is None:
        secret_value = _secrets().get_secret_value(SecretId=SIMULATOR_CREDS_SECRET_ARN)
        _CREDS = json.loads(secret_value["SecretString"])
    return _CREDS


def _get_token(force_refresh: bool = False) -> str:
    """
    Return a valid SPA-audience ID token.

    Refreshes when:
    - cache is empty (cold start)
    - token is within TOKEN_REFRESH_BUFFER_SECONDS of expiry (proactive)
    - caller explicitly requests force_refresh=True (reactive 401, etc.)
    """
    global _TOKEN, _TOKEN_EXPIRES_AT
    now = time.time()

    if force_refresh:
        logger.info("auth_force_refresh", reason="caller_requested")
    elif _TOKEN is None:
        logger.info("auth_cold_start")
    elif now >= (_TOKEN_EXPIRES_AT - TOKEN_REFRESH_BUFFER_SECONDS):
        logger.info(
            "auth_proactive_refresh",
            expires_at=int(_TOKEN_EXPIRES_AT),
            now=int(now),
            seconds_until_expiry=int(_TOKEN_EXPIRES_AT - now),
        )
    else:
        logger.debug("auth_cache_hit", seconds_until_expiry=int(_TOKEN_EXPIRES_AT - now))
        return _TOKEN

    creds = _load_creds()
    resp = _cognito().admin_initiate_auth(
        UserPoolId=COGNITO_USER_POOL_ID,
        ClientId=ADMIN_AUTH_CLIENT_ID,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": creds["username"], "PASSWORD": creds["password"]},
    )
    result = resp["AuthenticationResult"]
    _TOKEN = result["IdToken"]
    _TOKEN_EXPIRES_AT = now + result["ExpiresIn"]
    logger.info(
        "auth_token_issued",
        expires_in=result["ExpiresIn"],
        expires_at=int(_TOKEN_EXPIRES_AT),
    )
    return _TOKEN


# ────────────────────────────────────────────────────────────────────────────
# HTTP helper
# ────────────────────────────────────────────────────────────────────────────


def _api_call(method: str, url: str, body: dict | None = None, auth: bool = True) -> dict:
    """
    Make an authenticated API call. Single source of truth for all outbound HTTP.

    Returns: {"status": int, "data": dict|list|str|None, "ok": bool}
    Always pacing-sleeps API_PACING_SECONDS after the call to stay under WAF limits.
    Reactive 401-refresh: one retry with a fresh token; if that 401s, raise.
    """

    def _do_request(token: str | None) -> tuple[int, bytes]:
        headers = {
            "Content-Type": "application/json",
            "X-Correlation-Id": str(uuid.uuid4()),
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        encoded = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url=url, method=method, headers=headers, data=encoded)
        try:
            with open_https(req, allowed_hosts=_ALLOWED_API_HOSTS, timeout=20) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    token = _get_token() if auth else None
    status, raw = _do_request(token)

    if status == 401 and auth:
        logger.warning("auth_401_reactive_refresh", url=url, method=method)
        token = _get_token(force_refresh=True)
        status, raw = _do_request(token)
        if status == 401:
            logger.error("auth_401_after_refresh", url=url, method=method)
            raise RuntimeError(f"Auth failed after force-refresh: {method} {url}")

    time.sleep(API_PACING_SECONDS)

    parsed: Any = None
    if raw:
        try:
            parsed = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            parsed = raw.decode("utf-8", errors="replace")

    is_ok = 200 <= status < 300

    log_kwargs = {"method": method, "url": url, "status": status}
    if not is_ok:
        response_preview = (raw[:1024].decode("utf-8", errors="replace")) if raw else ""
        request_preview = json.dumps(body)[:512] if body is not None else ""
        logger.warning(
            "api_call_non_2xx",
            **log_kwargs,
            response_preview=response_preview,
            request_preview=request_preview,
        )
    else:
        logger.debug("api_call_ok", **log_kwargs)

    return {"status": status, "data": parsed, "ok": is_ok}


# ────────────────────────────────────────────────────────────────────────────
# Cached loaders — guest pool, property list
# ────────────────────────────────────────────────────────────────────────────


def _load_guest_pool() -> list[tuple[str, str]]:
    """Load the simulator guest pool as (guest_id, loyalty_tier) tuples. Cached after first call."""
    global _GUEST_POOL
    if _GUEST_POOL is not None:
        return _GUEST_POOL

    # Imported lazily to keep cold-start fast.
    from utils.database import get_conn

    started_at = time.time()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT guest_id, loyalty_tier FROM guests WHERE email LIKE 'simguest-%'"
        )
        rows = cur.fetchall()
    conn.commit()
    _GUEST_POOL = [(str(row["guest_id"]), row["loyalty_tier"] or "NONE") for row in rows]
    elapsed_ms = int((time.time() - started_at) * 1000)
    logger.info("guest_pool_loaded", count=len(_GUEST_POOL), elapsed_ms=elapsed_ms)
    return _GUEST_POOL


def _load_properties() -> list[dict]:
    """Load all 50 properties from the CRS API. Cached after first call."""
    global _PROPERTIES
    if _PROPERTIES is not None:
        return _PROPERTIES

    response = _api_call("GET", f"{CRS_API_URL}/properties?limit=200", auth=False)
    if not response["ok"]:
        logger.warning("properties_load_failed", status=response["status"])
        _PROPERTIES = []
        return _PROPERTIES

    raw = response["data"].get("data", [])
    _PROPERTIES = [p for p in raw if p.get("isActive")]
    logger.info("properties_loaded", count=len(_PROPERTIES))
    return _PROPERTIES


# ────────────────────────────────────────────────────────────────────────────
# Phase context manager
# ────────────────────────────────────────────────────────────────────────────


@contextmanager
def _phase(name: str, run_stats: dict):
    """
    Wrap a phase with start/end logs, duration tracking, and exception capture.
    Phase failure is logged via logger.exception() and recorded in stats; run continues.
    """
    started = time.time()
    stats = {"success": 0, "skip": 0, "error": 0}
    run_stats[name] = stats
    logger.info("phase_start", phase=name)
    try:
        yield stats
    except Exception:
        stats["error"] += 1
        logger.exception("phase_failed", phase=name)
    finally:
        duration_ms = int((time.time() - started) * 1000)
        logger.info(
            "phase_end",
            phase=name,
            success_count=stats["success"],
            skip_count=stats["skip"],
            error_count=stats["error"],
            duration_ms=duration_ms,
        )


# ────────────────────────────────────────────────────────────────────────────
# Phases
# ────────────────────────────────────────────────────────────────────────────


def _phase_check_out_guests(stats: dict) -> None:
    """Check out guests whose check_out_date <= today.

    Pages through CHECKED_IN stays (ascending by check-in date, the /stays default
    sort) and checks out those whose stay has ended (check_out_date <= today), up
    to MAX_CHECKOUTS_PER_RUN. A stay runs >= 1 night, so nothing checked in today
    can be due — once we reach today's check-ins we stop (the ascending sort means
    everything behind them is also not yet due). Still-active stays checked in
    earlier are stepped past via a forward cursor (same paging strategy as
    _phase_check_in_guests) so the next fetch resumes beyond them.

    Checkouts must keep pace with check-ins: every check-in eventually becomes a
    checkout, and if checkouts lag, rooms stay OCCUPIED and later arrivals can't
    be assigned a room. So this cap tracks MAX_CHECKINS_PER_RUN.
    """
    today = date.today().isoformat()
    page_size = 100
    processed = 0
    skipped = 0  # forward cursor: still-active/failed stays we stepped past

    while processed < MAX_CHECKOUTS_PER_RUN:
        page = (skipped // page_size) + 1
        response = _api_call(
            "GET",
            f"{PMS_API_URL}/stays?status=CHECKED_IN&page={page}&limit={page_size}",
        )
        if not response["ok"]:
            stats["error"] += 1
            return

        stays = response["data"].get("data", {}).get("stays", [])
        stays = stays[skipped % page_size:]  # skip rows already stepped past
        if not stays:
            break

        hit_today = False
        for stay in stays:
            if processed >= MAX_CHECKOUTS_PER_RUN:
                break
            if stay.get("checkInDate", "9999") >= today:
                # Checked in today: not due, and (ascending sort) nothing behind
                # it is due either.
                hit_today = True
                break
            if stay.get("checkOutDate", "9999") > today:
                # Still-active stay: leave CHECKED_IN, step past it.
                skipped += 1
                stats["skip"] += 1
                continue
            stay_id = stay.get("reservationId") or stay.get("stayId")
            result = _api_call(
                "POST",
                f"{PMS_API_URL}/stays/{stay_id}/checkout",
                {"expressCheckout": True},
            )
            if result["ok"]:
                logger.info("checkout_completed", reservationId=stay_id)
                stats["success"] += 1
                processed += 1
            else:
                # Leave it and step past so we don't re-hit it this run.
                logger.warning("checkout_failed", reservationId=stay_id, status=result["status"])
                stats["error"] += 1
                skipped += 1

        if hit_today:
            break


def _phase_process_housekeeping(stats: dict) -> None:
    """
    Drive the HousekeepingDispatchStateMachine forward:
    - PENDING/CLEANING tasks: assign (if PENDING) + complete
    - INSPECTING tasks: inspect (~85% pass / ~15% fail)
    """
    # Assign + complete cleaning tasks (PENDING + CLEANING are both valid for assign+complete).
    #
    # The HousekeepingDispatchStateMachine advances tasks asynchronously
    # (DIRTY->CLEANING->INSPECTING->AVAILABLE), and the check_out_guests phase
    # earlier in this same run dirties rooms that feed it. So a task we read as
    # PENDING can advance to CLEANING (or further) between our GET snapshot and
    # the follow-up call. The handlers correctly reject the now-invalid
    # transition with 409 INVALID_STATE. That's an expected race, not a failure:
    # count it as a skip, and on a PENDING-assign 409 fall through to complete
    # (the task is almost certainly CLEANING now, which IS completable).
    # Completing/inspecting a task moves it out of its status, so re-fetching
    # page 1 (limit is API-capped at 100) surfaces the next batch — this drains
    # the whole backlog up to MAX_HOUSEKEEPING_TASKS_PER_RUN instead of only the
    # first 100. A `seen` set guarantees termination: if a fetch returns only
    # tasks we've already handled (e.g. ones that erred and stayed put), there's
    # no forward progress, so we stop.
    for status_filter in ("PENDING", "CLEANING"):
        seen: set[str] = set()
        processed = 0
        while processed < MAX_HOUSEKEEPING_TASKS_PER_RUN:
            response = _api_call(
                "GET", f"{PMS_API_URL}/housekeeping/tasks?status={status_filter}&limit=100"
            )
            if not response["ok"]:
                stats["error"] += 1
                break

            tasks = response["data"].get("data", {}).get("tasks", [])
            fresh = [t for t in tasks if t["taskId"] not in seen]
            if not fresh:
                break

            for task in fresh:
                if processed >= MAX_HOUSEKEEPING_TASKS_PER_RUN:
                    break
                task_id = task["taskId"]
                seen.add(task_id)
                processed += 1

                if task["status"] == "PENDING":
                    assign_resp = _api_call(
                        "PUT",
                        f"{PMS_API_URL}/housekeeping/tasks/{task_id}/assign",
                        {"assignedTo": random.choice(HOUSEKEEPER_NAMES)},
                    )
                    if not assign_resp["ok"]:
                        if assign_resp["status"] == 409:
                            # State machine already advanced it past PENDING —
                            # benign race. Fall through to complete the (now
                            # CLEANING) task.
                            logger.info("hk_assign_raced", taskId=task_id, status=409)
                        else:
                            logger.warning("hk_assign_failed", taskId=task_id, status=assign_resp["status"])
                            stats["error"] += 1
                            continue

                complete_resp = _api_call(
                    "POST",
                    f"{PMS_API_URL}/housekeeping/tasks/{task_id}/complete",
                    {"notes": "Cleaning complete"},
                )
                if complete_resp["ok"]:
                    logger.info("hk_completed", taskId=task_id)
                    stats["success"] += 1
                elif complete_resp["status"] == 409:
                    # Task raced past the completable state (already INSPECTING/AVAILABLE).
                    logger.info("hk_complete_raced", taskId=task_id, status=409)
                    stats["skip"] += 1
                else:
                    stats["error"] += 1

    # Inspect — ~15% fail to exercise the re-clean loop. Same drain-by-refetch
    # loop: inspected tasks leave INSPECTING (pass -> INSPECTED, fail -> back to
    # CLEANING for next run).
    seen = set()
    processed = 0
    while processed < MAX_HOUSEKEEPING_TASKS_PER_RUN:
        inspect_resp = _api_call(
            "GET", f"{PMS_API_URL}/housekeeping/tasks?status=INSPECTING&limit=100"
        )
        if not inspect_resp["ok"]:
            stats["error"] += 1
            break

        tasks = inspect_resp["data"].get("data", {}).get("tasks", [])
        fresh = [t for t in tasks if t["taskId"] not in seen]
        if not fresh:
            break

        for task in fresh:
            if processed >= MAX_HOUSEKEEPING_TASKS_PER_RUN:
                break
            task_id = task["taskId"]
            seen.add(task_id)
            processed += 1
            passed = random.random() >= INSPECTION_FAIL_RATE
            result = _api_call(
                "POST",
                f"{PMS_API_URL}/housekeeping/tasks/{task_id}/inspect",
                {"passed": passed, "notes": "Inspection passed" if passed else "Re-clean required"},
            )
            if result["ok"]:
                logger.info("hk_inspected", taskId=task_id, passed=passed)
                stats["success"] += 1
            elif result["status"] == 409:
                # Task raced past INSPECTING (state machine advanced it). Benign.
                logger.info("hk_inspect_raced", taskId=task_id, status=409)
                stats["skip"] += 1
            else:
                stats["error"] += 1


def _phase_check_in_guests(stats: dict) -> None:
    """Check in CONFIRMED reservations whose check-in date has arrived.

    Pages through CONFIRMED reservations sorted ascending by check-in date (the
    /stays default sort) and checks in those whose date has arrived
    (check_in_date <= today), up to MAX_CHECKINS_PER_RUN. Because the list is
    ascending, all due reservations sit at the front and everything past the first
    future-dated row is not yet due — so we stop as soon as we see a future date.

    Paging strategy — two forces:
    - A successful check-in flips the reservation CONFIRMED -> CHECKED_IN, so it
      leaves the result set and the rows behind it shift toward the front.
    - A reservation can legitimately FAIL to check in (e.g. its room type is fully
      occupied at that property -> 409). Those stay CONFIRMED in the set.

    We therefore advance a forward cursor by the number of rows we DIDN'T remove
    (the skipped/failed ones), so the next fetch resumes past them rather than
    re-attempting them or clogging page 1. Successes don't advance the cursor
    because they drop out and pull later rows back.

    NOTE: we deliberately do NOT use the API's ?date= filter — that filters to
    stays *active on* the date (check_in <= date AND check_out >= date), which
    excludes reservations whose whole window is already in the past. We want all
    not-yet-checked-in reservations whose check-in date has arrived, so we filter
    client-side on check_in_date instead.
    """
    today = date.today().isoformat()
    page_size = 100
    processed = 0
    skipped = 0  # forward cursor: count of due rows we attempted but couldn't check in

    while processed < MAX_CHECKINS_PER_RUN:
        page = (skipped // page_size) + 1
        response = _api_call(
            "GET",
            f"{PMS_API_URL}/stays?status=CONFIRMED&page={page}&limit={page_size}",
        )
        if not response["ok"]:
            stats["error"] += 1
            return

        stays = response["data"].get("data", {}).get("stays", [])
        stays = stays[skipped % page_size:]  # skip rows already attempted this run
        if not stays:
            break  # no more CONFIRMED reservations at all

        hit_future = False
        for stay in stays:
            if processed >= MAX_CHECKINS_PER_RUN:
                break
            if stay.get("checkInDate", "9999") > today:
                hit_future = True
                break  # ascending sort: everything from here on is not yet due
            reservation_id = stay.get("reservationId")
            result = _api_call("POST", f"{PMS_API_URL}/stays/{reservation_id}/checkin", {})

            # If the booked room type is fully occupied at the property the check-in
            # 409s with NO_ROOM_AVAILABLE. A real front desk walks/upgrades the guest
            # to any open room, so we retry once with a roomId override pointing at an
            # AVAILABLE room of any type at that property. Without this, day-of stays
            # whose type is saturated lapse into permanent missed check-ins.
            if not result["ok"] and _is_no_room_available(result):
                walk_room_id = _find_available_room_id(stay.get("propertyId"))
                if walk_room_id:
                    result = _api_call(
                        "POST",
                        f"{PMS_API_URL}/stays/{reservation_id}/checkin",
                        {"roomId": walk_room_id},
                    )
                    if result["ok"]:
                        logger.info(
                            "checkin_walked", reservationId=reservation_id, roomId=walk_room_id
                        )

            processed += 1
            if result["ok"]:
                logger.info("checkin_completed", reservationId=reservation_id)
                stats["success"] += 1
            else:
                # Couldn't check in (e.g. no available room anywhere at the property).
                # Leave it CONFIRMED and advance the cursor so we step past it.
                logger.warning(
                    "checkin_skipped", reservationId=reservation_id, status=result["status"]
                )
                stats["skip"] += 1
                skipped += 1

        if hit_future:
            break  # reached future-dated reservations; nothing left due


def _is_no_room_available(result: dict) -> bool:
    """True if a check-in failed specifically because no room of the booked type
    was free (409 NO_ROOM_AVAILABLE) — as opposed to a bad-state or other error.
    Only this case warrants a walk to another room type.
    """
    if result.get("status") != 409:
        return False
    data = result.get("data")
    if not isinstance(data, dict):
        return False
    return (data.get("error") or {}).get("code") == "NO_ROOM_AVAILABLE"


def _find_available_room_id(property_id: str | None) -> str | None:
    """Return the roomId of any AVAILABLE room at the property, or None.

    Uses the room-status board endpoint, which lists per-room status for a single
    property. Picks the first AVAILABLE room regardless of type — the simulator
    only needs *a* room to walk the guest into.
    """
    if not property_id:
        return None
    response = _api_call(
        "GET", f"{PMS_API_URL}/housekeeping/rooms/summary?propertyId={property_id}"
    )
    if not response["ok"]:
        return None
    rooms = response["data"].get("data", {}).get("rooms", [])
    for room in rooms:
        if room.get("status") == "AVAILABLE":
            return room.get("roomId")
    return None


def _phase_cancel_no_shows(stats: dict) -> None:
    """Cancel reservations that lapsed without a check-in (no-shows).

    A CONFIRMED reservation whose check-out date is already in the past was never
    checked in and never will be — no real guest can arrive for a stay that has
    ended. Nothing else in the platform resolves these (the night audit only
    touches CHECKED_IN folios, and there is no NO_SHOW transition on the API), so
    without this sweep they accumulate forever as permanent "missed check-ins".

    We cancel via DELETE /reservations/{id} (the same path a guest cancellation
    uses), which sets status CANCELLED. Pages through CONFIRMED reservations
    ascending by check-in date.

    Termination/cursor: a stay is lapsed only when its whole window is past
    (check_out < today). Because the sort is by CHECK-IN date but lapse depends on
    CHECK-OUT date, and stays run 1–5 nights, a still-active stay can sit *before*
    a lapsed one — so we cannot stop at the first active row. We instead advance a
    forward cursor past non-lapsed rows (they stay CONFIRMED) and cancel lapsed
    ones (they drop out). We DO stop once check_in_date > today: every row past
    that is future-dated and therefore active, so none behind it can be lapsed.
    """
    today = date.today().isoformat()
    page_size = 100
    processed = 0
    skipped = 0  # forward cursor: rows scanned that were NOT cancelled

    while processed < MAX_NO_SHOW_CANCELS_PER_RUN:
        page = (skipped // page_size) + 1
        response = _api_call(
            "GET",
            f"{PMS_API_URL}/stays?status=CONFIRMED&page={page}&limit={page_size}",
        )
        if not response["ok"]:
            stats["error"] += 1
            return

        stays = response["data"].get("data", {}).get("stays", [])
        stays = stays[skipped % page_size:]
        if not stays:
            break

        hit_future = False
        for stay in stays:
            if processed >= MAX_NO_SHOW_CANCELS_PER_RUN:
                break
            if stay.get("checkInDate", "9999") > today:
                hit_future = True
                break  # future check-in: this and everything behind it is active
            if stay.get("checkOutDate", "9999") >= today:
                skipped += 1  # still-active stay: leave CONFIRMED, step past it
                continue
            reservation_id = stay.get("reservationId")
            result = _api_call(
                "DELETE",
                f"{CRS_API_URL}/reservations/{reservation_id}",
                {"cancellationReason": "Guest no-show"},
            )
            processed += 1
            if result["ok"]:
                logger.info("no_show_cancelled", reservationId=reservation_id)
                stats["success"] += 1
            else:
                logger.warning(
                    "no_show_cancel_failed",
                    reservationId=reservation_id,
                    status=result["status"],
                )
                stats["error"] += 1
                skipped += 1

        if hit_future:
            break


def _phase_add_incidental_charges(stats: dict) -> None:
    """Add SERVICE charges to OPEN folios."""
    response = _api_call("GET", f"{PMS_API_URL}/billing/folios?status=OPEN&limit=50")
    if not response["ok"]:
        stats["error"] += 1
        return

    folios = response["data"].get("data", {}).get("folios", [])
    if not folios:
        return

    for _ in range(MAX_INCIDENTAL_CHARGES_PER_RUN):
        folio = random.choice(folios)
        amount = round(random.uniform(8.0, 95.0), 2)
        result = _api_call(
            "POST",
            f"{PMS_API_URL}/billing/folios/{folio['folioId']}/charges",
            {
                "chargeType": "SERVICE",
                "description": random.choice(INCIDENTAL_DESCRIPTIONS),
                "amount": amount,
            },
        )
        if result["ok"]:
            logger.info("charge_posted", folioId=folio["folioId"], amount=amount)
            stats["success"] += 1
        else:
            stats["error"] += 1


def _phase_remove_charges(stats: dict) -> None:
    """Post negative ADJUSTMENT charges to ~40% of folios with SERVICE charges."""
    response = _api_call("GET", f"{PMS_API_URL}/billing/folios?status=OPEN&limit=50")
    if not response["ok"]:
        stats["error"] += 1
        return

    folios = response["data"].get("data", {}).get("folios", [])
    for folio in folios:
        if random.random() > 0.4:
            stats["skip"] += 1
            continue

        # Look up SERVICE charges on this folio to mirror an amount
        detail = _api_call("GET", f"{PMS_API_URL}/billing/folios/{folio['folioId']}")
        if not detail["ok"]:
            stats["error"] += 1
            continue

        charges = detail["data"].get("data", {}).get("charges", [])
        services = [c for c in charges if c.get("chargeType") == "SERVICE" and c.get("status") == "ACTIVE"]
        if not services:
            stats["skip"] += 1
            continue

        target = random.choice(services)
        amount = -float(target["amount"])
        result = _api_call(
            "POST",
            f"{PMS_API_URL}/billing/folios/{folio['folioId']}/charges",
            {
                "chargeType": "ADJUSTMENT",
                "description": f"Adjustment: {target.get('description', 'service')}",
                "amount": amount,
            },
        )
        if result["ok"]:
            logger.info("adjustment_posted", folioId=folio["folioId"], amount=amount)
            stats["success"] += 1
        else:
            stats["error"] += 1


def _load_active_windows() -> dict[str, list[tuple[date, date]]]:
    """
    For each simulator guest, return the list of (check_in, check_out) date pairs
    for their currently CONFIRMED or CHECKED_IN reservations. Used to skip guests
    who would double-book a window during the create_reservations phase.

    Loaded fresh per run (NOT module-cached) — the simulator both creates and
    cancels reservations, so the active set drifts within a single run too. We
    reload at the start of the booking phase and update the in-memory map as we
    create new reservations.
    """
    from utils.database import get_conn

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.guest_id, r.check_in_date, r.check_out_date
            FROM reservations r
            JOIN guests g ON g.guest_id = r.guest_id
            WHERE g.email LIKE 'simguest-%'
              AND r.status IN ('CONFIRMED', 'CHECKED_IN')
            """
        )
        rows = cur.fetchall()
    conn.commit()

    windows: dict[str, list[tuple[date, date]]] = {}
    for row in rows:
        gid = str(row["guest_id"])
        windows.setdefault(gid, []).append((row["check_in_date"], row["check_out_date"]))
    return windows


def _phase_create_reservations(stats: dict) -> None:
    """Drive the CRS booking flow: search → cart → book.

    Guest selection biases by loyalty tier (DIAMOND > GOLD > SILVER > NONE) and
    skips any guest who already holds an overlapping CONFIRMED/CHECKED_IN window.
    The "active windows" map is loaded once at phase start and updated in memory
    as we create new reservations during this run.

    Property selection is uniform across all available hotels: the search pulls
    up to SEARCH_CANDIDATE_LIMIT properties and picks one at random, so bookings
    spread across the portfolio instead of funneling into the featured few.
    """
    pool = _load_guest_pool()
    properties = _load_properties()
    if not pool or not properties:
        logger.warning(
            "create_reservations_unavailable", pool_size=len(pool), property_count=len(properties)
        )
        return

    active_windows = _load_active_windows()
    weights = [TIER_WEIGHTS.get(tier, 1) for (_, tier) in pool]

    today = date.today()
    overlap_skips = 0

    for _ in range(MAX_RESERVATIONS_PER_RUN):
        nights = random.randint(1, 5)
        check_in = today + timedelta(days=random.randint(1, FORWARD_WINDOW_DAYS))
        check_out = check_in + timedelta(days=nights)

        # Pick a guest whose existing windows don't overlap this one. Try up to
        # 10 weighted draws; if every draw conflicts, skip this iteration.
        guest_id = None
        for _attempt in range(10):
            candidate, _tier = random.choices(pool, weights=weights, k=1)[0]
            existing = active_windows.get(candidate, [])
            if not any(check_in < e_out and e_in < check_out for (e_in, e_out) in existing):
                guest_id = candidate
                break
        if guest_id is None:
            overlap_skips += 1
            stats["skip"] += 1
            continue

        # Step 1: search (public)
        search_body = {
            "checkIn": check_in.isoformat(),
            "checkOut": check_out.isoformat(),
            "adults": random.randint(1, 3),
            # Span all available properties (not just the top few featured ones)
            # so random.choice below spreads bookings across the whole portfolio.
            "limit": SEARCH_CANDIDATE_LIMIT,
        }
        search = _api_call("POST", f"{CRS_API_URL}/booking/search", search_body, auth=False)
        if not search["ok"]:
            logger.warning("create_reservation_failed", step="search", guestId=guest_id, status=search["status"])
            stats["error"] += 1
            continue

        # /booking/search returns data as a flat list; each item has cheapestOption with the rate plan.
        results = search["data"].get("data") or []
        if not results:
            logger.info("create_reservation_skipped", step="search", reason="no_results", guestId=guest_id)
            stats["skip"] += 1
            continue

        choice = random.choice(results)
        property_id = choice.get("propertyId")
        cheapest = choice.get("cheapestOption") or {}
        room_type_id = cheapest.get("roomTypeId")
        rate_plan_id = cheapest.get("ratePlanId")
        if not (property_id and room_type_id and rate_plan_id):
            logger.info("create_reservation_skipped", step="search", reason="missing_ids", guestId=guest_id)
            stats["skip"] += 1
            continue

        # Step 2: create cart (public)
        cart_body = {
            "propertyId": property_id,
            "roomTypeId": room_type_id,
            "ratePlanId": rate_plan_id,
            "checkIn": check_in.isoformat(),
            "checkOut": check_out.isoformat(),
            "sessionId": f"sim-{uuid.uuid4().hex}",
            "adults": search_body["adults"],
        }
        cart = _api_call("POST", f"{CRS_API_URL}/booking/cart", cart_body, auth=False)
        if not cart["ok"]:
            logger.warning("create_reservation_failed", step="cart", guestId=guest_id, status=cart["status"], propertyId=property_id)
            stats["error"] += 1
            continue

        cart_id = cart["data"].get("data", {}).get("cartId")
        if not cart_id:
            logger.warning("create_reservation_failed", step="cart", reason="no_cart_id_in_response", guestId=guest_id)
            stats["error"] += 1
            continue

        # Step 3: complete booking (JWT — operate-as-guest + Stripe sentinel)
        sim_pi = f"pi_simulated_{uuid.uuid4().hex[:24]}"
        book_body = {
            "guestId": guest_id,
            "paymentMethodId": sim_pi,
            "guests": [{"firstName": "Simulator", "lastName": "Guest", "email": "noreply@anycompanyhotels.local"}],
        }
        book = _api_call("POST", f"{CRS_API_URL}/booking/cart/{cart_id}/book", book_body)
        if book["ok"]:
            data = book["data"].get("data", {})
            res_id = (data.get("reservation") or {}).get("reservationId")
            confirmation = data.get("confirmationNumber")
            logger.info(
                "reservation_created",
                step="book",
                reservationId=res_id,
                confirmationNumber=confirmation,
                guestId=guest_id,
            )
            active_windows.setdefault(guest_id, []).append((check_in, check_out))
            stats["success"] += 1
        else:
            logger.warning("create_reservation_failed", step="book", guestId=guest_id, cartId=cart_id, status=book["status"])
            stats["error"] += 1

    if overlap_skips:
        logger.info("create_reservations_overlap_skips", count=overlap_skips)


def _phase_cancel_reservations(stats: dict) -> None:
    """Cancel up to MAX_CANCELLATIONS_PER_RUN future CONFIRMED reservations."""
    today = date.today().isoformat()
    response = _api_call("GET", f"{PMS_API_URL}/stays?status=CONFIRMED&limit=100")
    if not response["ok"]:
        stats["error"] += 1
        return

    stays = response["data"].get("data", {}).get("stays", [])
    future = [s for s in stays if s.get("checkInDate", "0000") > today]
    if not future:
        return

    cancellations = random.sample(future, min(len(future), MAX_CANCELLATIONS_PER_RUN))
    for stay in cancellations:
        reservation_id = stay.get("reservationId")
        result = _api_call(
            "DELETE",
            f"{CRS_API_URL}/reservations/{reservation_id}",
            {"cancellationReason": "Cancelled by guest"},
        )
        if result["ok"]:
            logger.info("reservation_cancelled", reservationId=reservation_id)
            stats["success"] += 1
        else:
            stats["error"] += 1


# ────────────────────────────────────────────────────────────────────────────
# Handler
# ────────────────────────────────────────────────────────────────────────────


@logger.inject_lambda_context
def handler(event, context):
    """Run end-to-end activity simulation."""
    run_id = uuid.uuid4().hex
    logger.append_keys(run_id=run_id)
    logger.info("run_start")

    run_stats: dict[str, dict] = {}

    with _phase("check_out_guests", run_stats) as s:
        _phase_check_out_guests(s)

    with _phase("process_housekeeping", run_stats) as s:
        _phase_process_housekeeping(s)

    with _phase("check_in_guests", run_stats) as s:
        _phase_check_in_guests(s)

    with _phase("cancel_no_shows", run_stats) as s:
        _phase_cancel_no_shows(s)

    with _phase("add_incidental_charges", run_stats) as s:
        _phase_add_incidental_charges(s)

    with _phase("remove_charges", run_stats) as s:
        _phase_remove_charges(s)

    with _phase("create_reservations", run_stats) as s:
        _phase_create_reservations(s)

    with _phase("cancel_reservations", run_stats) as s:
        _phase_cancel_reservations(s)

    logger.info("run_summary", stats=run_stats)
    return {"runId": run_id, "stats": run_stats}
