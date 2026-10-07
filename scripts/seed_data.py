"""
Seed data script for AnyCompany Hotels & Resorts.

Generates 50 US properties (10 regions x 5 cities), each with 3-6 room types,
50-400 rooms, BAR rate plan, and 365 days of availability.

Usage:
    python seed_data.py --host <db_host> --dbname hotel_crs --user anycompany_admin --password <pwd>

    Or with environment variables:
    DB_HOST=... DB_NAME=hotel_crs DB_USER=anycompany_admin DB_PASSWORD=... python seed_data.py
"""
import argparse
import os
import random
import uuid
from datetime import date, timedelta

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    print("Install psycopg: pip install 'psycopg[binary]'")
    raise


# ── Region/City Data ──

REGIONS = {
    "Northeast": [
        ("New York", "NY", "America/New_York", 40.7128, -74.0060),
        ("Boston", "MA", "America/New_York", 42.3601, -71.0589),
        ("Philadelphia", "PA", "America/New_York", 39.9526, -75.1652),
        ("Washington", "DC", "America/New_York", 38.9072, -77.0369),
        ("Providence", "RI", "America/New_York", 41.8240, -71.4128),
    ],
    "Southeast": [
        ("Miami", "FL", "America/New_York", 25.7617, -80.1918),
        ("Charleston", "SC", "America/New_York", 32.7765, -79.9311),
        ("Savannah", "GA", "America/New_York", 32.0809, -81.0912),
        ("Nashville", "TN", "America/Chicago", 36.1627, -86.7816),
        ("Atlanta", "GA", "America/New_York", 33.7490, -84.3880),
    ],
    "Florida": [
        ("Orlando", "FL", "America/New_York", 28.5383, -81.3792),
        ("Tampa", "FL", "America/New_York", 27.9506, -82.4572),
        ("Key West", "FL", "America/New_York", 24.5551, -81.7800),
        ("Fort Lauderdale", "FL", "America/New_York", 26.1224, -80.1373),
        ("Jacksonville", "FL", "America/New_York", 30.3322, -81.6557),
    ],
    "Midwest": [
        ("Chicago", "IL", "America/Chicago", 41.8781, -87.6298),
        ("Minneapolis", "MN", "America/Chicago", 44.9778, -93.2650),
        ("Detroit", "MI", "America/Detroit", 42.3314, -83.0458),
        ("Cleveland", "OH", "America/New_York", 41.4993, -81.6944),
        ("Indianapolis", "IN", "America/Indiana/Indianapolis", 39.7684, -86.1581),
    ],
    "Texas": [
        ("Austin", "TX", "America/Chicago", 30.2672, -97.7431),
        ("Dallas", "TX", "America/Chicago", 32.7767, -96.7970),
        ("Houston", "TX", "America/Chicago", 29.7604, -95.3698),
        ("San Antonio", "TX", "America/Chicago", 29.4241, -98.4936),
        ("Fort Worth", "TX", "America/Chicago", 32.7555, -97.3308),
    ],
    "Mountain": [
        ("Denver", "CO", "America/Denver", 39.7392, -104.9903),
        ("Salt Lake City", "UT", "America/Denver", 40.7608, -111.8910),
        ("Boise", "ID", "America/Boise", 43.6150, -116.2023),
        ("Albuquerque", "NM", "America/Denver", 35.0844, -106.6504),
        ("Scottsdale", "AZ", "America/Phoenix", 33.4942, -111.9261),
    ],
    "Pacific NW": [
        ("Seattle", "WA", "America/Los_Angeles", 47.6062, -122.3321),
        ("Portland", "OR", "America/Los_Angeles", 45.5152, -122.6784),
        ("Bend", "OR", "America/Los_Angeles", 44.0582, -121.3153),
        ("Spokane", "WA", "America/Los_Angeles", 47.6588, -117.4260),
        ("Olympia", "WA", "America/Los_Angeles", 47.0379, -122.9007),
    ],
    "California": [
        ("San Francisco", "CA", "America/Los_Angeles", 37.7749, -122.4194),
        ("Los Angeles", "CA", "America/Los_Angeles", 34.0522, -118.2437),
        ("San Diego", "CA", "America/Los_Angeles", 32.7157, -117.1611),
        ("Napa", "CA", "America/Los_Angeles", 38.2975, -122.2869),
        ("Santa Barbara", "CA", "America/Los_Angeles", 34.4208, -119.6982),
    ],
    "Hawaii": [
        ("Honolulu", "HI", "Pacific/Honolulu", 21.3069, -157.8583),
        ("Maui", "HI", "Pacific/Honolulu", 20.7984, -156.3319),
        ("Kauai", "HI", "Pacific/Honolulu", 22.0964, -159.5261),
        ("Big Island", "HI", "Pacific/Honolulu", 19.8968, -155.5828),
        ("Lanai", "HI", "Pacific/Honolulu", 20.8283, -156.9220),
    ],
    "Special": [
        ("Anchorage", "AK", "America/Anchorage", 61.2181, -149.9003),
        ("Juneau", "AK", "America/Anchorage", 58.3005, -134.4197),
        ("Aspen", "CO", "America/Denver", 39.1911, -106.8175),
        ("Park City", "UT", "America/Denver", 40.6461, -111.4980),
        ("Jackson Hole", "WY", "America/Denver", 43.4799, -110.7624),
    ],
}

# ── Hotel Name Templates ──

HOTEL_PREFIXES = [
    "AnyCompany", "The AnyCompany", "AnyCompany Grand", "AnyCompany Resort &",
    "AnyCompany Suites", "AnyCompany Plaza", "AnyCompany Tower", "AnyCompany Park",
    "AnyCompany Bay", "AnyCompany Vista",
]

HOTEL_SUFFIXES = [
    "Hotel", "Resort", "Spa", "Inn", "Lodge",
    "Boutique Hotel", "Hotel & Spa", "Residences", "Retreat", "Club",
]

# ── Room Type Templates ──

ROOM_TYPE_TEMPLATES = [
    {
        "code": "STD-K",
        "name": "Standard King",
        "description": "Comfortable room featuring a plush king bed, work desk, and modern amenities.",
        "max_occupancy": 2,
        "bed_configuration": "1 King",
        "square_feet": 325,
        "base_rate_range": (149, 249),
        "amenities": ["WiFi", "TV", "Mini Fridge", "Coffee Maker", "Iron"],
    },
    {
        "code": "STD-Q",
        "name": "Standard Double Queen",
        "description": "Spacious room with two queen beds, ideal for families or friends traveling together.",
        "max_occupancy": 4,
        "bed_configuration": "2 Queens",
        "square_feet": 375,
        "base_rate_range": (159, 269),
        "amenities": ["WiFi", "TV", "Mini Fridge", "Coffee Maker", "Iron"],
    },
    {
        "code": "DLX-K",
        "name": "Deluxe King",
        "description": "Upgraded room with premium king bed, sitting area, and enhanced city or garden views.",
        "max_occupancy": 2,
        "bed_configuration": "1 King",
        "square_feet": 425,
        "base_rate_range": (199, 349),
        "amenities": ["WiFi", "TV", "Mini Bar", "Coffee Maker", "Iron", "Bathrobe", "Slippers"],
    },
    {
        "code": "DLX-Q",
        "name": "Deluxe Double Queen",
        "description": "Premium double queen room with expanded living space and upgraded furnishings.",
        "max_occupancy": 4,
        "bed_configuration": "2 Queens",
        "square_feet": 475,
        "base_rate_range": (219, 369),
        "amenities": ["WiFi", "TV", "Mini Bar", "Coffee Maker", "Iron", "Bathrobe"],
    },
    {
        "code": "STE-JR",
        "name": "Junior Suite",
        "description": "Open-plan suite with king bed, separate sitting area, and premium bathroom with soaking tub.",
        "max_occupancy": 2,
        "bed_configuration": "1 King",
        "square_feet": 550,
        "base_rate_range": (299, 499),
        "amenities": ["WiFi", "TV", "Mini Bar", "Coffee Maker", "Iron", "Bathrobe", "Slippers", "Soaking Tub"],
    },
    {
        "code": "STE-EX",
        "name": "Executive Suite",
        "description": "Full suite with separate bedroom, living room, dining area, and panoramic views.",
        "max_occupancy": 4,
        "bed_configuration": "1 King + Sofa Bed",
        "square_feet": 750,
        "base_rate_range": (449, 799),
        "amenities": ["WiFi", "TV", "Mini Bar", "Coffee Maker", "Iron", "Bathrobe", "Slippers", "Soaking Tub", "Dining Area", "Living Room"],
    },
    {
        "code": "STE-PR",
        "name": "Presidential Suite",
        "description": "Our finest accommodation featuring multiple rooms, butler service, and the best views in the house.",
        "max_occupancy": 6,
        "bed_configuration": "1 King + 2 Queens",
        "square_feet": 1200,
        "base_rate_range": (899, 2499),
        "amenities": ["WiFi", "TV", "Mini Bar", "Coffee Maker", "Iron", "Bathrobe", "Slippers", "Soaking Tub", "Dining Area", "Living Room", "Butler Service", "Private Terrace"],
    },
    {
        "code": "ADA-K",
        "name": "Accessible King",
        "description": "ADA-compliant room with roll-in shower, lowered fixtures, and king bed.",
        "max_occupancy": 2,
        "bed_configuration": "1 King",
        "square_feet": 375,
        "base_rate_range": (149, 249),
        "accessibility_type": "MOBILITY",
        "amenities": ["WiFi", "TV", "Mini Fridge", "Coffee Maker", "Iron", "Roll-in Shower"],
    },
]

# ── Property Amenities ──

PROPERTY_AMENITIES_POOL = [
    "Pool", "Fitness Center", "Spa", "Restaurant", "Bar/Lounge",
    "Business Center", "Concierge", "Room Service", "Valet Parking",
    "Free WiFi", "Pet Friendly", "Airport Shuttle", "Electric Vehicle Charging",
    "Rooftop Terrace", "Golf Course", "Tennis Courts", "Beach Access",
    "Ski-in/Ski-out", "Hot Tub", "Sauna",
]


def generate_property_code(city, region_index, city_index):
    """Generate a unique property code like ANY-NYC-0001."""
    city_code = "".join(c for c in city.upper() if c.isalpha())[:3]
    return f"ANY-{city_code}-{region_index:02d}{city_index:02d}"


def generate_hotel_name(city):
    """Generate a hotel name."""
    prefix = random.choice(HOTEL_PREFIXES)
    suffix = random.choice(HOTEL_SUFFIXES)
    return f"{prefix} {city} {suffix}"


def generate_property_description(city, state, star_rating):
    """Generate a property description."""
    descriptors = {
        5: "luxury",
        4: "upscale",
        3: "contemporary",
    }
    style = descriptors.get(star_rating, "comfortable")
    return (
        f"Experience {style} hospitality at our {city}, {state} location. "
        f"Featuring world-class amenities, exceptional dining, and a prime location "
        f"in the heart of {city}."
    )


def get_room_types_for_property(star_rating, total_rooms):
    """Select room types appropriate for the property's star rating."""
    if star_rating >= 5:
        # Luxury: all types including presidential
        templates = random.sample(ROOM_TYPE_TEMPLATES, min(6, len(ROOM_TYPE_TEMPLATES)))
    elif star_rating >= 4:
        # Upscale: standard through executive, sometimes junior
        templates = ROOM_TYPE_TEMPLATES[:6]
        templates = random.sample(templates, min(5, len(templates)))
    else:
        # Standard: basics only
        templates = ROOM_TYPE_TEMPLATES[:4]
        templates = random.sample(templates, min(3, len(templates)))

    # Always include accessible room
    ada = ROOM_TYPE_TEMPLATES[-1]
    if ada not in templates:
        templates.append(ada)

    return templates


def distribute_rooms(total_rooms, num_types):
    """Distribute total rooms across room types (more standards, fewer suites)."""
    weights = list(range(num_types, 0, -1))
    total_weight = sum(weights)
    distribution = [max(2, int(total_rooms * w / total_weight)) for w in weights]
    # Adjust to match total
    diff = total_rooms - sum(distribution)
    distribution[0] += diff
    return distribution


def generate_address(city, state):
    """Generate a plausible street address."""
    number = random.randint(1, 999)
    streets = [
        "Main Street", "Broadway", "Park Avenue", "Market Street",
        "Ocean Drive", "Peachtree Street", "Michigan Avenue",
        "Congress Avenue", "Pike Street", "Union Square",
        "Harbor Boulevard", "Riverside Drive", "Sunset Boulevard",
    ]
    return f"{number} {random.choice(streets)}"


def seed_database(conn):
    """Seed all data into the database."""
    cur = conn.cursor()

    print("Seeding properties, room types, rooms, rates, and availability...")

    property_count = 0
    today = date.today()

    for region_idx, (_region_name, cities) in enumerate(REGIONS.items()):
        for city_idx, (city, state, tz, lat, lng) in enumerate(cities):
            property_id = str(uuid.uuid4())
            star_rating = random.choice([3, 4, 4, 4, 5])
            total_rooms = random.randint(50, 400)
            is_featured = property_count < 10  # First 10 are featured
            code = generate_property_code(city, region_idx, city_idx + 1)
            name = generate_hotel_name(city)
            description = generate_property_description(city, state, star_rating)
            address = generate_address(city, state)
            zip_code = f"{random.randint(10000, 99999)}"
            phone = f"+1-{random.randint(200,999)}-{random.randint(200,999)}-{random.randint(1000,9999)}"
            email = f"info@{code.lower().replace('-', '')}.anycompanyhotels.com"
            website = f"https://www.anycompanyhotels.com/{code.lower()}"

            num_amenities = random.randint(6, 12)
            amenities = random.sample(PROPERTY_AMENITIES_POOL, num_amenities)

            # Insert property
            cur.execute("""
                INSERT INTO properties (
                    property_id, code, name, description, address, city, state,
                    zip_code, country, latitude, longitude, phone, email, website,
                    star_rating, timezone, total_rooms, amenities,
                    is_featured, is_active
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s
                )
            """, (
                property_id, code, name, description, address, city, state,
                zip_code, "US", lat, lng, phone, email, website,
                star_rating, tz, total_rooms, amenities,
                is_featured, True,
            ))

            # Generate room types
            room_templates = get_room_types_for_property(star_rating, total_rooms)
            room_counts = distribute_rooms(total_rooms, len(room_templates))

            # Create BAR (Best Available Rate) rate plan
            rate_plan_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO rate_plans (
                    rate_plan_id, property_id, code, name, description,
                    type, discount_type, discount_value,
                    valid_from, valid_to, cancellation_policy, is_active
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s
                )
            """, (
                rate_plan_id, property_id, "BAR", "Best Available Rate",
                "Our standard flexible rate with free cancellation up to 24 hours before check-in.",
                "PUBLIC", "PERCENTAGE", 0,
                today, today + timedelta(days=730),
                "FLEXIBLE", True,
            ))

            for rt_idx, (template, room_count) in enumerate(zip(room_templates, room_counts, strict=True)):
                room_type_id = str(uuid.uuid4())

                # Scale base rate by star rating
                rate_min, rate_max = template["base_rate_range"]
                multiplier = 1.0 + (star_rating - 3) * 0.3
                base_rate = round(random.uniform(rate_min, rate_max) * multiplier, 2)

                cur.execute("""
                    INSERT INTO room_types (
                        room_type_id, property_id, code, name, description,
                        max_occupancy, bed_configuration, square_feet, base_rate,
                        accessibility_type, smoking_allowed, amenities,
                        sort_order, is_active
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s
                    )
                """, (
                    room_type_id, property_id, template["code"], template["name"],
                    template["description"], template["max_occupancy"],
                    template["bed_configuration"], template["square_feet"], base_rate,
                    template.get("accessibility_type"), False, template["amenities"],
                    rt_idx, True,
                ))

                # Create rate_plan_room_prices for BAR
                cur.execute("""
                    INSERT INTO rate_plan_room_prices (rate_plan_id, room_type_id, price_per_night)
                    VALUES (%s, %s, %s)
                """, (rate_plan_id, room_type_id, base_rate))

                # Create rooms
                floor_count = max(2, total_rooms // 40)
                for room_idx in range(room_count):
                    room_id = str(uuid.uuid4())
                    floor = (room_idx % floor_count) + 1
                    room_number = f"{floor}{rt_idx}{(room_idx // floor_count + 1):02d}"

                    cur.execute("""
                        INSERT INTO rooms (
                            room_id, property_id, room_type_id, room_number,
                            floor, status, is_active
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        room_id, property_id, room_type_id, room_number,
                        # PMS uses AVAILABLE for ready-to-occupy rooms (the
                        # original CRS schema defaulted to CLEAN, which migration
                        # 005 also rewrites to AVAILABLE). Inserting AVAILABLE
                        # directly keeps the dashboard counts correct on fresh
                        # deployments without a follow-up status migration.
                        floor, "AVAILABLE", True,
                    ))

                # Create 365 days of availability
                for day_offset in range(365):
                    avail_date = today + timedelta(days=day_offset)
                    # Weekend/holiday premium: slightly reduce availability
                    base_sold = 0
                    if avail_date.weekday() >= 4:  # Fri-Sat
                        base_sold = random.randint(0, max(1, room_count // 5))

                    cur.execute("""
                        INSERT INTO availability (
                            room_type_id, date, property_id,
                            total_inventory, sold, blocked
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        room_type_id, avail_date, property_id,
                        room_count, base_sold, 0,
                    ))

            property_count += 1
            if property_count % 10 == 0:
                print(f"  ...{property_count} properties seeded")
                conn.commit()

    conn.commit()
    print(f"Total properties seeded: {property_count}")

    # ── Seed Promo Codes ──
    print("Seeding promo codes...")
    promo_codes = [
        {
            "code": "ANYCOMPANY10",
            "description": "10% off your stay at any AnyCompany Hotel property",
            "discount_type": "PERCENTAGE",
            "discount_value": 10.00,
            "max_uses": 10000,
            "min_stay_nights": 1,
            "min_booking_amount": 0,
            "valid_from": today,
            "valid_to": today + timedelta(days=365),
        },
        {
            "code": "SUMMER25",
            "description": "$25 off your booking",
            "discount_type": "FIXED_AMOUNT",
            "discount_value": 25.00,
            "max_uses": 5000,
            "min_stay_nights": 2,
            "min_booking_amount": 100,
            "valid_from": today,
            "valid_to": today + timedelta(days=365),
        },
        {
            "code": "WELCOME",
            "description": "15% off your first booking",
            "discount_type": "PERCENTAGE",
            "discount_value": 15.00,
            "max_uses": 50000,
            "min_stay_nights": 1,
            "min_booking_amount": 0,
            "valid_from": today,
            "valid_to": today + timedelta(days=365),
        },
    ]

    for promo in promo_codes:
        cur.execute("""
            INSERT INTO promo_codes (
                promo_id, code, description, discount_type, discount_value,
                max_uses, used_count, valid_from, valid_to,
                min_stay_nights, min_booking_amount, is_active
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s
            )
        """, (
            str(uuid.uuid4()), promo["code"], promo["description"],
            promo["discount_type"], promo["discount_value"],
            promo["max_uses"], 0, promo["valid_from"], promo["valid_to"],
            promo["min_stay_nights"], promo["min_booking_amount"], True,
        ))

    conn.commit()
    print("Promo codes seeded: ANYCOMPANY10, SUMMER25, WELCOME")
    print("Seed complete!")


def main():
    parser = argparse.ArgumentParser(description="Seed AnyCompany Hotel database")
    parser.add_argument("--host", default=os.environ.get("DB_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DB_PORT", "5432")))
    parser.add_argument("--dbname", default=os.environ.get("DB_NAME", "hotel_crs"))
    parser.add_argument("--user", default=os.environ.get("DB_USER", "anycompany_admin"))
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD", ""))
    args = parser.parse_args()

    conn_str = f"host={args.host} port={args.port} dbname={args.dbname} user={args.user} password={args.password}"
    print(f"Connecting to {args.host}:{args.port}/{args.dbname}...")

    with psycopg.connect(conn_str, row_factory=dict_row) as conn:
        seed_database(conn)


if __name__ == "__main__":
    main()
