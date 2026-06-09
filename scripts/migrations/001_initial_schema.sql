-- ============================================================================
-- AnyCompany Hotels & Resorts — Central Reservation System (hotel_crs)
-- Migration 001: Initial Schema
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ----------------------------------------------------------------------------
-- Updated-at trigger function
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 1. properties
-- ============================================================================
CREATE TABLE properties (
    property_id     UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    code            VARCHAR         NOT NULL UNIQUE,
    name            VARCHAR         NOT NULL,
    description     TEXT,
    address         VARCHAR,
    city            VARCHAR,
    state           VARCHAR,
    zip_code        VARCHAR,
    country         VARCHAR         DEFAULT 'US',
    latitude        NUMERIC(10,7),
    longitude       NUMERIC(10,7),
    phone           VARCHAR,
    email           VARCHAR,
    website         VARCHAR,
    star_rating     INTEGER         CHECK (star_rating BETWEEN 1 AND 5),
    timezone        VARCHAR         DEFAULT 'America/New_York',
    check_in_time   TIME            DEFAULT '15:00',
    check_out_time  TIME            DEFAULT '11:00',
    total_rooms     INTEGER,
    amenities       TEXT[],
    hero_image_url  VARCHAR,
    image_urls      TEXT[],
    is_featured     BOOLEAN         DEFAULT false,
    is_active       BOOLEAN         DEFAULT true,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX idx_properties_city        ON properties (city);
CREATE INDEX idx_properties_state       ON properties (state);
CREATE INDEX idx_properties_is_featured ON properties (is_featured);
CREATE INDEX idx_properties_is_active   ON properties (is_active);

CREATE TRIGGER trg_properties_updated_at
    BEFORE UPDATE ON properties
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 2. room_types
-- ============================================================================
CREATE TABLE room_types (
    room_type_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id         UUID            NOT NULL REFERENCES properties (property_id),
    code                VARCHAR         NOT NULL,
    name                VARCHAR         NOT NULL,
    description         TEXT,
    max_occupancy       INTEGER,
    bed_configuration   VARCHAR,
    square_feet         INTEGER,
    base_rate           NUMERIC(10,2),
    accessibility_type  VARCHAR,
    smoking_allowed     BOOLEAN         DEFAULT false,
    amenities           TEXT[],
    image_urls          TEXT[],
    sort_order          INTEGER         DEFAULT 0,
    is_active           BOOLEAN         DEFAULT true,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (property_id, code)
);

CREATE INDEX idx_room_types_property_id ON room_types (property_id);

CREATE TRIGGER trg_room_types_updated_at
    BEFORE UPDATE ON room_types
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 3. rooms
-- ============================================================================
CREATE TABLE rooms (
    room_id             UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id         UUID            NOT NULL REFERENCES properties (property_id),
    room_type_id        UUID            NOT NULL REFERENCES room_types (room_type_id),
    room_number         VARCHAR         NOT NULL,
    floor               INTEGER,
    wing                VARCHAR,
    status              VARCHAR         DEFAULT 'CLEAN'
                                        CHECK (status IN ('CLEAN', 'DIRTY', 'INSPECTED', 'OUT_OF_ORDER', 'OUT_OF_INVENTORY')),
    is_connecting       BOOLEAN         DEFAULT false,
    connecting_room_id  UUID            REFERENCES rooms (room_id),
    features            TEXT[],
    last_cleaned_at     TIMESTAMPTZ,
    is_active           BOOLEAN         DEFAULT true,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (property_id, room_number)
);

CREATE INDEX idx_rooms_property_id  ON rooms (property_id);
CREATE INDEX idx_rooms_room_type_id ON rooms (room_type_id);

CREATE TRIGGER trg_rooms_updated_at
    BEFORE UPDATE ON rooms
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 4. availability
-- ============================================================================
CREATE TABLE availability (
    room_type_id            UUID            NOT NULL REFERENCES room_types (room_type_id),
    date                    DATE            NOT NULL,
    property_id             UUID            NOT NULL REFERENCES properties (property_id),
    total_inventory         INTEGER         NOT NULL,
    sold                    INTEGER         DEFAULT 0,
    blocked                 INTEGER         DEFAULT 0,
    available               INTEGER         GENERATED ALWAYS AS (total_inventory - sold - blocked) STORED,
    overbooking_allowance   INTEGER         DEFAULT 0,
    updated_at              TIMESTAMPTZ     DEFAULT NOW(),
    PRIMARY KEY (room_type_id, date)
);

CREATE INDEX idx_availability_property_date   ON availability (property_id, date);
CREATE INDEX idx_availability_room_type_date  ON availability (room_type_id, date);

CREATE TRIGGER trg_availability_updated_at
    BEFORE UPDATE ON availability
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 5. rate_plans
-- ============================================================================
CREATE TABLE rate_plans (
    rate_plan_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id         UUID            NOT NULL REFERENCES properties (property_id),
    code                VARCHAR         NOT NULL,
    name                VARCHAR         NOT NULL,
    description         TEXT,
    type                VARCHAR         CHECK (type IN ('PUBLIC', 'NEGOTIATED', 'LOYALTY', 'PACKAGE', 'PROMOTIONAL')),
    discount_type       VARCHAR         CHECK (discount_type IN ('PERCENTAGE', 'FIXED_AMOUNT', 'ABSOLUTE')),
    discount_value      NUMERIC(10,2)   DEFAULT 0,
    valid_from          DATE,
    valid_to            DATE,
    cancellation_policy VARCHAR         CHECK (cancellation_policy IN ('FLEXIBLE', 'MODERATE', 'STRICT', 'NON_REFUNDABLE')),
    restrictions        JSONB           DEFAULT '{}',
    is_active           BOOLEAN         DEFAULT true,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE (property_id, code)
);

CREATE INDEX idx_rate_plans_property_id  ON rate_plans (property_id);
CREATE INDEX idx_rate_plans_valid_dates  ON rate_plans (valid_from, valid_to);

CREATE TRIGGER trg_rate_plans_updated_at
    BEFORE UPDATE ON rate_plans
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 6. rate_plan_room_prices
-- ============================================================================
CREATE TABLE rate_plan_room_prices (
    rate_plan_id    UUID            NOT NULL REFERENCES rate_plans (rate_plan_id),
    room_type_id    UUID            NOT NULL REFERENCES room_types (room_type_id),
    price_per_night NUMERIC(10,2)   NOT NULL,
    PRIMARY KEY (rate_plan_id, room_type_id)
);

-- ============================================================================
-- 7. rate_overrides
-- ============================================================================
CREATE TABLE rate_overrides (
    rate_plan_id    UUID            NOT NULL REFERENCES rate_plans (rate_plan_id),
    override_date   DATE            NOT NULL,
    room_type_id    UUID            NOT NULL REFERENCES room_types (room_type_id),
    override_amount NUMERIC(10,2)   NOT NULL,
    reason          VARCHAR,
    created_by      VARCHAR,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    PRIMARY KEY (rate_plan_id, override_date)
);

-- ============================================================================
-- 8. packages
-- ============================================================================
CREATE TABLE packages (
    package_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR         NOT NULL,
    description     TEXT,
    rate_plan_id    UUID            NOT NULL REFERENCES rate_plans (rate_plan_id),
    inclusions      TEXT[],
    inclusion_values JSONB          DEFAULT '{}',
    image_url       VARCHAR,
    is_active       BOOLEAN         DEFAULT true,
    valid_from      DATE,
    valid_to        DATE,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE TRIGGER trg_packages_updated_at
    BEFORE UPDATE ON packages
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 9. guests
-- ============================================================================
CREATE TABLE guests (
    guest_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    cognito_sub     VARCHAR         UNIQUE NOT NULL,
    first_name      VARCHAR,
    last_name       VARCHAR,
    email           VARCHAR         UNIQUE NOT NULL,
    email_verified  BOOLEAN         DEFAULT false,
    phone           VARCHAR,
    phone_verified  BOOLEAN         DEFAULT false,
    date_of_birth   DATE,
    nationality     VARCHAR,
    language        VARCHAR         DEFAULT 'en',
    address_line1   VARCHAR,
    address_line2   VARCHAR,
    address_line3   VARCHAR,
    address_line4   VARCHAR,
    city            VARCHAR,
    state           VARCHAR,
    province        VARCHAR,
    county          VARCHAR,
    postal_code     VARCHAR,
    country         VARCHAR,
    preferences     JSONB           DEFAULT '{}',
    comm_prefs      JSONB           DEFAULT '{"email_opt_in": true, "sms_opt_in": false, "push_opt_in": false, "marketing_opt_in": false}',
    stripe_customer_id VARCHAR,
    loyalty_id      UUID,
    vip_level       VARCHAR         DEFAULT 'NONE'
                                    CHECK (vip_level IN ('NONE', 'SILVER', 'GOLD', 'PLATINUM')),
    total_stays     INTEGER         DEFAULT 0,
    total_spend     NUMERIC(12,2)   DEFAULT 0,
    last_stay_date  DATE,
    tags            TEXT[],
    merged_from_ids UUID[],
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX idx_guests_cognito_sub ON guests (cognito_sub);
CREATE INDEX idx_guests_email       ON guests (email);

CREATE TRIGGER trg_guests_updated_at
    BEFORE UPDATE ON guests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 10. guest_identity_documents
-- ============================================================================
CREATE TABLE guest_identity_documents (
    document_id     UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id        UUID            NOT NULL REFERENCES guests (guest_id),
    type            VARCHAR         NOT NULL
                                    CHECK (type IN ('PASSPORT', 'DRIVERS_LICENSE', 'ID_CARD')),
    number          VARCHAR         NOT NULL,  -- encrypted at application layer
    issuing_country VARCHAR,
    expiry_date     DATE,
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- ============================================================================
-- 11. stored_payment_methods
-- ============================================================================
CREATE TABLE stored_payment_methods (
    payment_method_id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id                UUID        NOT NULL REFERENCES guests (guest_id),
    stripe_payment_method_id VARCHAR    NOT NULL,
    stripe_customer_id      VARCHAR,
    type                    VARCHAR     DEFAULT 'CARD'
                                        CHECK (type IN ('CARD', 'BANK_ACCOUNT', 'VOUCHER')),
    last4                   VARCHAR(4),
    brand                   VARCHAR,
    exp_month               INTEGER,
    exp_year                INTEGER,
    name_on_card            VARCHAR,
    is_default              BOOLEAN     DEFAULT false,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE TRIGGER trg_stored_payment_methods_updated_at
    BEFORE UPDATE ON stored_payment_methods
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 12. reservations
-- ============================================================================
CREATE TABLE reservations (
    reservation_id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    confirmation_number         VARCHAR         UNIQUE NOT NULL,
    guest_id                    UUID            NOT NULL REFERENCES guests (guest_id),
    property_id                 UUID            NOT NULL REFERENCES properties (property_id),
    room_type_id                UUID            NOT NULL REFERENCES room_types (room_type_id),
    rate_plan_id                UUID            NOT NULL REFERENCES rate_plans (rate_plan_id),
    loyalty_membership_id       UUID,
    payment_method_id           UUID            REFERENCES stored_payment_methods (payment_method_id),
    group_block_id              UUID,
    status                      VARCHAR         DEFAULT 'CONFIRMED'
                                                CHECK (status IN ('CONFIRMED', 'CHECKED_IN', 'CHECKED_OUT', 'CANCELLED', 'NO_SHOW')),
    trip_type                   VARCHAR         DEFAULT 'LEISURE',
    brand_code                  VARCHAR         DEFAULT 'ANY',
    hotel_code                  VARCHAR,
    number_of_nights            INTEGER,
    number_of_guests            INTEGER,
    adults                      INTEGER         DEFAULT 1,
    children                    INTEGER         DEFAULT 0,
    same_day_booking            BOOLEAN         DEFAULT false,
    reserver                    VARCHAR,
    additional_notes            TEXT,

    -- Snapshot fields (frozen at booking time)
    booked_rate_plan_code       VARCHAR,
    booked_rate_plan_name       VARCHAR,
    booked_rate_plan_description TEXT,
    amount_per_night            NUMERIC(10,2),
    total_before_tax            NUMERIC(10,2),
    total_after_tax             NUMERIC(10,2),
    deposit_amount              NUMERIC(10,2)   DEFAULT 0,
    refundable                  BOOLEAN         DEFAULT true,
    guarantee_type              VARCHAR         DEFAULT 'CREDIT_CARD',
    currency_code               VARCHAR(3)      DEFAULT 'USD',
    currency_name               VARCHAR         DEFAULT 'US Dollar',
    currency_symbol             VARCHAR(1)      DEFAULT '$',
    booked_room_type_code       VARCHAR,
    booked_room_type_name       VARCHAR,
    booked_loyalty_tier         VARCHAR,
    booked_loyalty_program_name VARCHAR,

    -- Stay dates
    check_in_date               DATE            NOT NULL,
    early_check_in_requested    BOOLEAN         DEFAULT false,
    late_check_in_requested     BOOLEAN         DEFAULT false,
    check_out_date              DATE            NOT NULL,
    early_check_out_requested   BOOLEAN         DEFAULT false,
    late_check_out_requested    BOOLEAN         DEFAULT false,
    self_check_out_requested    BOOLEAN         DEFAULT false,

    -- Channel info
    channel_creation_id         VARCHAR,
    channel_last_updated_id     VARCHAR,
    channel_method              VARCHAR         DEFAULT 'WEB',
    channel_reservation_id      VARCHAR,

    -- Cancellation
    cancellation_reason         VARCHAR,
    cancellation_comment        TEXT,
    cancellation_charge         NUMERIC(10,2)   DEFAULT 0,
    cancelled_at                TIMESTAMPTZ,

    -- Audit / tracing
    context_id                  VARCHAR,
    transaction_id              VARCHAR,
    agent_id                    VARCHAR,
    processed_date              TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ     DEFAULT NOW(),
    created_by                  VARCHAR,
    updated_at                  TIMESTAMPTZ     DEFAULT NOW(),
    updated_by                  VARCHAR,
    attributes                  JSONB           DEFAULT '{}'
);

CREATE INDEX idx_reservations_guest_id              ON reservations (guest_id);
CREATE INDEX idx_reservations_property_id           ON reservations (property_id);
CREATE INDEX idx_reservations_confirmation_number   ON reservations (confirmation_number);
CREATE INDEX idx_reservations_check_in_date         ON reservations (check_in_date);
CREATE INDEX idx_reservations_status                ON reservations (status);

CREATE TRIGGER trg_reservations_updated_at
    BEFORE UPDATE ON reservations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 13. reservation_services
-- ============================================================================
CREATE TABLE reservation_services (
    service_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id  UUID            NOT NULL REFERENCES reservations (reservation_id),
    service_type    VARCHAR,
    description     TEXT,
    cost            NUMERIC(10,2),
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- ============================================================================
-- 14. payment_authorizations
-- ============================================================================
CREATE TABLE payment_authorizations (
    authorization_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    stay_id                 UUID,
    reservation_id          UUID            NOT NULL REFERENCES reservations (reservation_id),
    guest_id                UUID            NOT NULL REFERENCES guests (guest_id),
    stripe_payment_intent_id VARCHAR        NOT NULL,
    stripe_customer_id      VARCHAR,
    amount                  NUMERIC(10,2),
    currency                VARCHAR(3)      DEFAULT 'USD',
    status                  VARCHAR         DEFAULT 'AUTHORIZED'
                                            CHECK (status IN ('AUTHORIZED', 'CAPTURED', 'VOIDED', 'EXPIRED')),
    last4                   VARCHAR(4),
    card_brand              VARCHAR,
    expires_at              TIMESTAMPTZ,
    created_at              TIMESTAMPTZ     DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX idx_payment_auth_reservation_id        ON payment_authorizations (reservation_id);
CREATE INDEX idx_payment_auth_stripe_intent_id      ON payment_authorizations (stripe_payment_intent_id);

CREATE TRIGGER trg_payment_authorizations_updated_at
    BEFORE UPDATE ON payment_authorizations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 15. payment_captures
-- ============================================================================
CREATE TABLE payment_captures (
    capture_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    authorization_id UUID           NOT NULL REFERENCES payment_authorizations (authorization_id),
    folio_id        UUID,
    captured_amount NUMERIC(10,2),
    stripe_charge_id VARCHAR,
    receipt_url     TEXT,
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- ============================================================================
-- 16. payment_refunds
-- ============================================================================
CREATE TABLE payment_refunds (
    refund_id       UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    capture_id      UUID            NOT NULL REFERENCES payment_captures (capture_id),
    stripe_refund_id VARCHAR,
    amount          NUMERIC(10,2),
    reason          VARCHAR         CHECK (reason IN ('EARLY_DEPARTURE', 'SERVICE_RECOVERY', 'BILLING_ERROR', 'CANCELLATION')),
    status          VARCHAR         DEFAULT 'PENDING'
                                    CHECK (status IN ('PENDING', 'SUCCEEDED', 'FAILED')),
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE TRIGGER trg_payment_refunds_updated_at
    BEFORE UPDATE ON payment_refunds
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 17. vouchers
-- ============================================================================
CREATE TABLE vouchers (
    voucher_id      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id        UUID            REFERENCES guests (guest_id),
    code            VARCHAR         UNIQUE NOT NULL,
    discount_type   VARCHAR         CHECK (discount_type IN ('PERCENTAGE', 'FIXED_AMOUNT')),
    discount_value  NUMERIC(10,2),
    discount_code   VARCHAR,
    max_uses        INTEGER,
    used_count      INTEGER         DEFAULT 0,
    valid_from      DATE,
    valid_to        DATE,
    is_active       BOOLEAN         DEFAULT true,
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- ============================================================================
-- 18. promo_codes
-- ============================================================================
CREATE TABLE promo_codes (
    promo_id            UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    code                VARCHAR         UNIQUE NOT NULL,
    description         TEXT,
    discount_type       VARCHAR         CHECK (discount_type IN ('PERCENTAGE', 'FIXED_AMOUNT')),
    discount_value      NUMERIC(10,2),
    max_uses            INTEGER,
    used_count          INTEGER         DEFAULT 0,
    valid_from          DATE,
    valid_to            DATE,
    min_stay_nights     INTEGER         DEFAULT 1,
    min_booking_amount  NUMERIC(10,2)   DEFAULT 0,
    applicable_properties UUID[],
    is_active           BOOLEAN         DEFAULT true,
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

-- ============================================================================
-- 19. booking_carts
-- ============================================================================
CREATE TABLE booking_carts (
    cart_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id        UUID            REFERENCES guests (guest_id),
    session_id      VARCHAR         NOT NULL,
    property_id     UUID            NOT NULL REFERENCES properties (property_id),
    room_type_id    UUID            NOT NULL REFERENCES room_types (room_type_id),
    rate_plan_id    UUID            NOT NULL REFERENCES rate_plans (rate_plan_id),
    check_in_date   DATE,
    check_out_date  DATE,
    adults          INTEGER         DEFAULT 1,
    children        INTEGER         DEFAULT 0,
    amount_per_night NUMERIC(10,2),
    total_before_tax NUMERIC(10,2),
    total_after_tax NUMERIC(10,2),
    promo_code      VARCHAR,
    discount_amount NUMERIC(10,2)   DEFAULT 0,
    status          VARCHAR         DEFAULT 'ACTIVE'
                                    CHECK (status IN ('ACTIVE', 'EXPIRED', 'CONVERTED')),
    expires_at      TIMESTAMPTZ     NOT NULL,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX idx_booking_carts_session_id   ON booking_carts (session_id);
CREATE INDEX idx_booking_carts_guest_id     ON booking_carts (guest_id);
CREATE INDEX idx_booking_carts_expires_at   ON booking_carts (expires_at);

CREATE TRIGGER trg_booking_carts_updated_at
    BEFORE UPDATE ON booking_carts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- End of migration 001
-- ============================================================================
