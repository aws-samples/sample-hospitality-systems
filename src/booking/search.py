"""
Lambda handler for POST /booking/search.

Searches properties with available rooms for the specified date range.
Public endpoint — no authentication required.

For each matching property, returns the cheapest available room type rate.
Results are sorted by featured status (descending) then by cheapest price
(ascending), with pagination support.
"""

from utils.logger import get_logger
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from utils.database import get_conn
from utils.response import ok, bad_request, server_error, transform_keys
from utils.validation import parse_body, require_fields, validate_date, validate_date_range

logger = get_logger("booking")


def _serialize(value):
    """Convert non-JSON-serializable types to strings."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_row(row):
    """Serialize all values in a row dict."""
    return {k: _serialize(v) for k, v in row.items()}


def handler(event, context):
    """Search properties with available rooms for a date range."""
    try:
        body = parse_body(event)
        field_error = require_fields(body, ["checkIn", "checkOut"])
        if field_error:
            return field_error

        check_in = body["checkIn"]
        check_out = body["checkOut"]
        city = body.get("city") or body.get("destination")
        state = body.get("state")
        adults = body.get("adults", 1)
        children = body.get("children", 0)
        min_price = body.get("minPrice")
        max_price = body.get("maxPrice")
        amenities = body.get("amenities")
        page = body.get("page", 1)
        limit = body.get("limit", 20)

        # Validate dates
        date_error = validate_date_range(check_in, check_out)
        if date_error:
            return date_error

        ci = validate_date(check_in)
        co = validate_date(check_out)
        num_nights = (co - ci).days

        # Validate pagination
        try:
            page = int(page)
            limit = int(limit)
        except (ValueError, TypeError):
            return bad_request("Invalid page or limit value.")

        if page < 1:
            page = 1
        if limit < 1:
            limit = 1
        if limit > 100:
            limit = 100
        offset = (page - 1) * limit

        total_guests = int(adults) + int(children)

        # Prepare filter values; optional ones are None when absent.
        city_lower = city.lower() if city else None
        state_lower = state.lower() if state else None
        amenities_val = amenities if (amenities and isinstance(amenities, list) and len(amenities) > 0) else None
        min_price_val = Decimal(str(min_price)) if min_price is not None else None
        max_price_val = Decimal(str(max_price)) if max_price is not None else None

        # Build the shared param list for the inner CTE + outer WHERE.
        # Param order (positional):
        #   [0]  total_guests      — rt.max_occupancy >= %s
        #   [1]  check_in          — generate_series start
        #   [2]  check_out         — generate_series end
        #   [3]  check_in          — rp.valid_from <= %s
        #   [4]  check_out         — rp.valid_to >= %s
        #   [5]  num_nights        — total_before_tax multiplier
        #   [6]  num_nights        — total_after_tax multiplier
        #   [7]  city_lower        — IS NULL test
        #   [8]  city_lower        — LOWER(p.city) match
        #   [9]  state_lower       — IS NULL test
        #   [10] state_lower       — p.state match
        #   [11] amenities_val     — IS NULL test
        #   [12] amenities_val     — p.amenities @> match
        #   [13] min_price_val     — IS NULL test
        #   [14] min_price_val     — >= match
        #   [15] max_price_val     — IS NULL test
        #   [16] max_price_val     — <= match
        # The CTE body has 5 placeholders (max_occupancy, generate_series start/
        # end, rate-plan valid_from/valid_to).
        cte_params = [
            total_guests,
            check_in,
            check_out,
            check_in,
            check_out,
        ]
        # The outer WHERE filter placeholders (each optional value bound twice:
        # once for the IS NULL test, once for the match). Identical for both the
        # count and fetch queries.
        filter_params = [
            city_lower, city_lower,
            state_lower, state_lower,
            amenities_val, amenities_val,
            min_price_val, min_price_val,
            max_price_val, max_price_val,
        ]
        # The fetch query's outer SELECT additionally has two num_nights
        # placeholders (total_before_tax / total_after_tax multipliers) BETWEEN
        # the CTE body and the WHERE clause. The count query's SELECT is just
        # p.property_id, so it omits those two.
        count_params = cte_params + filter_params
        fetch_params = cte_params + [num_nights, num_nights] + filter_params

        conn = get_conn()
        try:
            # Count query — wraps the full CTE as a subquery.
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS total FROM ("
                    "WITH available_room_types AS ("
                    "    SELECT"
                    "        rt.room_type_id,"
                    "        rt.property_id,"
                    "        rt.name AS room_type_name,"
                    "        rt.code AS room_type_code,"
                    "        rt.max_occupancy,"
                    "        rt.bed_configuration,"
                    "        rt.amenities AS room_amenities,"
                    "        rt.image_urls AS room_image_urls"
                    "    FROM room_types rt"
                    "    WHERE rt.is_active = TRUE"
                    "      AND rt.max_occupancy >= %s"
                    "      AND NOT EXISTS ("
                    "          SELECT 1"
                    "          FROM generate_series(%s::date, %s::date - INTERVAL '1 day', '1 day') AS d(dt)"
                    "          LEFT JOIN availability a"
                    "            ON a.room_type_id = rt.room_type_id AND a.date = d.dt::date"
                    "          WHERE COALESCE(a.available, 0) + COALESCE(a.overbooking_allowance, 0) <= 0"
                    "      )"
                    "),"
                    "cheapest_rates AS ("
                    "    SELECT"
                    "        art.room_type_id,"
                    "        art.property_id,"
                    "        art.room_type_name,"
                    "        art.room_type_code,"
                    "        art.max_occupancy,"
                    "        art.bed_configuration,"
                    "        art.room_amenities,"
                    "        art.room_image_urls,"
                    "        rp.rate_plan_id,"
                    "        rp.name AS rate_plan_name,"
                    "        rp.code AS rate_plan_code,"
                    "        rp.cancellation_policy,"
                    "        rprp.price_per_night,"
                    "        CASE"
                    "            WHEN rp.discount_type = 'PERCENTAGE'"
                    "                THEN rprp.price_per_night * (1 - rp.discount_value / 100)"
                    "            WHEN rp.discount_type = 'FIXED_AMOUNT'"
                    "                THEN rprp.price_per_night - rp.discount_value"
                    "            ELSE rprp.price_per_night"
                    "        END AS effective_nightly_rate,"
                    "        ROW_NUMBER() OVER ("
                    "            PARTITION BY art.property_id"
                    "            ORDER BY"
                    "                CASE"
                    "                    WHEN rp.discount_type = 'PERCENTAGE'"
                    "                        THEN rprp.price_per_night * (1 - rp.discount_value / 100)"
                    "                    WHEN rp.discount_type = 'FIXED_AMOUNT'"
                    "                        THEN rprp.price_per_night - rp.discount_value"
                    "                    ELSE rprp.price_per_night"
                    "                END ASC"
                    "        ) AS rn"
                    "    FROM available_room_types art"
                    "    JOIN rate_plan_room_prices rprp ON rprp.room_type_id = art.room_type_id"
                    "    JOIN rate_plans rp ON rp.rate_plan_id = rprp.rate_plan_id"
                    "        AND rp.property_id = art.property_id"
                    "        AND rp.is_active = TRUE"
                    "        AND (rp.valid_from IS NULL OR rp.valid_from <= %s)"
                    "        AND (rp.valid_to IS NULL OR rp.valid_to >= %s)"
                    ")"
                    "SELECT p.property_id"
                    " FROM properties p"
                    " JOIN cheapest_rates cr ON cr.property_id = p.property_id AND cr.rn = 1"
                    " WHERE p.is_active = TRUE"
                    " AND (%s::text IS NULL OR LOWER(p.city) = %s::text)"
                    " AND (%s::text IS NULL OR LOWER(p.state) = %s::text)"
                    " AND (%s::text[] IS NULL OR p.amenities @> %s::text[])"
                    " AND (%s::numeric IS NULL OR cr.effective_nightly_rate >= %s::numeric)"
                    " AND (%s::numeric IS NULL OR cr.effective_nightly_rate <= %s::numeric)"
                    ") AS search_results",
                    count_params,
                )
                total = cur.fetchone()["total"]

            # Fetch query — same CTE, full column list, ORDER BY + LIMIT/OFFSET.
            with conn.cursor() as cur:
                cur.execute(
                    "WITH available_room_types AS ("
                    "    SELECT"
                    "        rt.room_type_id,"
                    "        rt.property_id,"
                    "        rt.name AS room_type_name,"
                    "        rt.code AS room_type_code,"
                    "        rt.max_occupancy,"
                    "        rt.bed_configuration,"
                    "        rt.amenities AS room_amenities,"
                    "        rt.image_urls AS room_image_urls"
                    "    FROM room_types rt"
                    "    WHERE rt.is_active = TRUE"
                    "      AND rt.max_occupancy >= %s"
                    "      AND NOT EXISTS ("
                    "          SELECT 1"
                    "          FROM generate_series(%s::date, %s::date - INTERVAL '1 day', '1 day') AS d(dt)"
                    "          LEFT JOIN availability a"
                    "            ON a.room_type_id = rt.room_type_id AND a.date = d.dt::date"
                    "          WHERE COALESCE(a.available, 0) + COALESCE(a.overbooking_allowance, 0) <= 0"
                    "      )"
                    "),"
                    "cheapest_rates AS ("
                    "    SELECT"
                    "        art.room_type_id,"
                    "        art.property_id,"
                    "        art.room_type_name,"
                    "        art.room_type_code,"
                    "        art.max_occupancy,"
                    "        art.bed_configuration,"
                    "        art.room_amenities,"
                    "        art.room_image_urls,"
                    "        rp.rate_plan_id,"
                    "        rp.name AS rate_plan_name,"
                    "        rp.code AS rate_plan_code,"
                    "        rp.cancellation_policy,"
                    "        rprp.price_per_night,"
                    "        CASE"
                    "            WHEN rp.discount_type = 'PERCENTAGE'"
                    "                THEN rprp.price_per_night * (1 - rp.discount_value / 100)"
                    "            WHEN rp.discount_type = 'FIXED_AMOUNT'"
                    "                THEN rprp.price_per_night - rp.discount_value"
                    "            ELSE rprp.price_per_night"
                    "        END AS effective_nightly_rate,"
                    "        ROW_NUMBER() OVER ("
                    "            PARTITION BY art.property_id"
                    "            ORDER BY"
                    "                CASE"
                    "                    WHEN rp.discount_type = 'PERCENTAGE'"
                    "                        THEN rprp.price_per_night * (1 - rp.discount_value / 100)"
                    "                    WHEN rp.discount_type = 'FIXED_AMOUNT'"
                    "                        THEN rprp.price_per_night - rp.discount_value"
                    "                    ELSE rprp.price_per_night"
                    "                END ASC"
                    "        ) AS rn"
                    "    FROM available_room_types art"
                    "    JOIN rate_plan_room_prices rprp ON rprp.room_type_id = art.room_type_id"
                    "    JOIN rate_plans rp ON rp.rate_plan_id = rprp.rate_plan_id"
                    "        AND rp.property_id = art.property_id"
                    "        AND rp.is_active = TRUE"
                    "        AND (rp.valid_from IS NULL OR rp.valid_from <= %s)"
                    "        AND (rp.valid_to IS NULL OR rp.valid_to >= %s)"
                    ")"
                    "SELECT"
                    "    p.property_id,"
                    "    p.code AS property_code,"
                    "    p.name AS property_name,"
                    "    p.description AS property_description,"
                    "    p.address,"
                    "    p.city,"
                    "    p.state,"
                    "    p.zip_code,"
                    "    p.country,"
                    "    p.latitude,"
                    "    p.longitude,"
                    "    p.phone,"
                    "    p.star_rating,"
                    "    p.amenities AS property_amenities,"
                    "    p.hero_image_url,"
                    "    p.image_urls AS property_image_urls,"
                    "    p.is_featured,"
                    "    p.check_in_time,"
                    "    p.check_out_time,"
                    "    cr.room_type_id,"
                    "    cr.room_type_name,"
                    "    cr.room_type_code,"
                    "    cr.max_occupancy,"
                    "    cr.bed_configuration,"
                    "    cr.rate_plan_id,"
                    "    cr.rate_plan_name,"
                    "    cr.rate_plan_code,"
                    "    cr.cancellation_policy,"
                    "    cr.price_per_night,"
                    "    cr.effective_nightly_rate,"
                    "    (cr.effective_nightly_rate * %s) AS total_before_tax,"
                    "    (cr.effective_nightly_rate * %s * 1.12) AS total_after_tax"
                    " FROM properties p"
                    " JOIN cheapest_rates cr ON cr.property_id = p.property_id AND cr.rn = 1"
                    " WHERE p.is_active = TRUE"
                    " AND (%s::text IS NULL OR LOWER(p.city) = %s::text)"
                    " AND (%s::text IS NULL OR LOWER(p.state) = %s::text)"
                    " AND (%s::text[] IS NULL OR p.amenities @> %s::text[])"
                    " AND (%s::numeric IS NULL OR cr.effective_nightly_rate >= %s::numeric)"
                    " AND (%s::numeric IS NULL OR cr.effective_nightly_rate <= %s::numeric)"
                    " ORDER BY p.is_featured DESC, cr.effective_nightly_rate ASC"
                    " LIMIT %s OFFSET %s",
                    fetch_params + [limit, offset],
                )
                rows = cur.fetchall()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        # Format results
        results = []
        for row in rows:
            results.append({
                "property_id": str(row["property_id"]),
                "property_code": row["property_code"],
                "property_name": row["property_name"],
                "property_description": row["property_description"],
                "address": row["address"],
                "city": row["city"],
                "state": row["state"],
                "zip_code": row["zip_code"],
                "country": row["country"],
                "latitude": str(row["latitude"]) if row["latitude"] else None,
                "longitude": str(row["longitude"]) if row["longitude"] else None,
                "phone": row["phone"],
                "star_rating": row["star_rating"],
                "property_amenities": row["property_amenities"],
                "hero_image_url": row["hero_image_url"],
                "is_featured": row["is_featured"],
                "check_in_time": str(row["check_in_time"]) if row["check_in_time"] else None,
                "check_out_time": str(row["check_out_time"]) if row["check_out_time"] else None,
                "cheapest_option": {
                    "room_type_id": str(row["room_type_id"]),
                    "room_type_name": row["room_type_name"],
                    "room_type_code": row["room_type_code"],
                    "max_occupancy": row["max_occupancy"],
                    "bed_configuration": row["bed_configuration"],
                    "rate_plan_id": str(row["rate_plan_id"]),
                    "rate_plan_name": row["rate_plan_name"],
                    "rate_plan_code": row["rate_plan_code"],
                    "cancellation_policy": row["cancellation_policy"],
                    "price_per_night": str(row["effective_nightly_rate"]),
                    "total_before_tax": str(row["total_before_tax"]),
                    "total_after_tax": str(row["total_after_tax"]),
                    "num_nights": num_nights,
                },
            })

        total_pages = (total + limit - 1) // limit if limit > 0 else 1

        return ok(results, metadata={
            "pagination": {
                "page": page,
                "limit": limit,
                "total_items": total,
                "total_pages": total_pages,
            },
            "search_criteria": {
                "check_in": check_in,
                "check_out": check_out,
                "adults": adults,
                "children": children,
                "city": city,
                "state": state,
                "num_nights": num_nights,
            },
        })

    except Exception as e:
        logger.exception("Error searching properties")
        return server_error("Failed to search properties.")
