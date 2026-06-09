-- Migration 003: PMS Schema Extension
-- Adds tables for PMS operations: check-in/out, housekeeping, billing, loyalty, night audit
-- Run via: python scripts/run_migration.py --sql-file scripts/migrations/003_pms_schema.sql

BEGIN;

--------------------------------------------------------------------------------
-- Modify existing tables
--------------------------------------------------------------------------------

-- Add loyalty columns to guests
ALTER TABLE guests
    ADD COLUMN IF NOT EXISTS loyalty_tier VARCHAR(20) NOT NULL DEFAULT 'NONE',
    ADD COLUMN IF NOT EXISTS total_stays INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS points_balance INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS lifetime_points_earned INTEGER NOT NULL DEFAULT 0;

-- Add PMS lifecycle columns to reservations
ALTER TABLE reservations
    ADD COLUMN IF NOT EXISTS lifecycle_execution_arn VARCHAR(500),
    ADD COLUMN IF NOT EXISTS check_in_task_token TEXT,
    ADD COLUMN IF NOT EXISTS check_out_task_token TEXT,
    ADD COLUMN IF NOT EXISTS checked_in_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS checked_out_at TIMESTAMPTZ;

--------------------------------------------------------------------------------
-- New table: checkinout_records
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS checkinout_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id UUID NOT NULL REFERENCES reservations(reservation_id),
    property_id UUID NOT NULL REFERENCES properties(property_id),
    guest_id UUID NOT NULL,
    room_id UUID NOT NULL,
    room_number VARCHAR(20),
    record_type VARCHAR(10) NOT NULL CHECK (record_type IN ('CHECKIN', 'CHECKOUT')),
    performed_by VARCHAR(100),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_checkinout_reservation ON checkinout_records(reservation_id);
CREATE INDEX IF NOT EXISTS idx_checkinout_property ON checkinout_records(property_id, recorded_at);

--------------------------------------------------------------------------------
-- New table: housekeeping_tasks
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS housekeeping_tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id UUID NOT NULL REFERENCES properties(property_id),
    room_id UUID NOT NULL REFERENCES rooms(room_id),
    room_number VARCHAR(20),
    task_type VARCHAR(20) NOT NULL CHECK (task_type IN ('CHECKOUT', 'PRE_ARRIVAL', 'MAINTENANCE')),
    priority VARCHAR(10) NOT NULL DEFAULT 'NORMAL' CHECK (priority IN ('HIGH', 'NORMAL', 'LOW')),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'ASSIGNED', 'CLEANING', 'COMPLETED', 'INSPECTING', 'INSPECTED', 'FAILED')),
    assigned_to VARCHAR(100),
    notes VARCHAR(2000),
    cleaning_task_token TEXT,
    inspection_task_token TEXT,
    reservation_id UUID,
    execution_arn VARCHAR(500),
    completed_at TIMESTAMPTZ,
    inspected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tasks_property_status ON housekeeping_tasks(property_id, status);

--------------------------------------------------------------------------------
-- New table: folios
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS folios (
    folio_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id UUID NOT NULL REFERENCES reservations(reservation_id),
    property_id UUID NOT NULL REFERENCES properties(property_id),
    guest_id UUID NOT NULL REFERENCES guests(guest_id),
    check_in_date DATE,
    check_out_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'PENDING_PAYMENT', 'PAID', 'VOID', 'PAYMENT_FAILED')),
    subtotal NUMERIC(10,2),
    tax_amount NUMERIC(10,2),
    total_amount NUMERIC(10,2),
    payment_method VARCHAR(50),
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_folios_reservation ON folios(reservation_id);
CREATE INDEX IF NOT EXISTS idx_folios_property_status ON folios(property_id, status);

--------------------------------------------------------------------------------
-- New table: charges
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS charges (
    charge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folio_id UUID NOT NULL REFERENCES folios(folio_id),
    charge_type VARCHAR(20) NOT NULL CHECK (charge_type IN ('ROOM_RATE', 'TAX', 'SERVICE', 'ADJUSTMENT')),
    description VARCHAR(500),
    amount NUMERIC(10,2) NOT NULL,
    charge_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'VOIDED')),
    voided_at TIMESTAMPTZ,
    voided_by VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_charges_folio ON charges(folio_id);

--------------------------------------------------------------------------------
-- New table: payments
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    payment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folio_id UUID NOT NULL REFERENCES folios(folio_id),
    reservation_id UUID,
    guest_id UUID,
    amount NUMERIC(10,2) NOT NULL,
    method VARCHAR(50),
    stripe_payment_intent_id VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'APPROVED' CHECK (status IN ('APPROVED', 'DECLINED', 'REFUNDED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payments_folio ON payments(folio_id);

--------------------------------------------------------------------------------
-- New table: loyalty_transactions
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS loyalty_transactions (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id UUID NOT NULL REFERENCES guests(guest_id),
    reservation_id UUID REFERENCES reservations(reservation_id),
    transaction_type VARCHAR(30) NOT NULL CHECK (transaction_type IN ('EARN_STAY', 'REDEEM_NIGHT', 'ADJUSTMENT')),
    points INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    description VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_loyalty_guest ON loyalty_transactions(guest_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_loyalty_reservation ON loyalty_transactions(reservation_id) WHERE reservation_id IS NOT NULL;

--------------------------------------------------------------------------------
-- New table: night_audit_runs
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS night_audit_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_date DATE NOT NULL,
    property_id UUID NOT NULL,
    metrics JSONB,
    triggered_by VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (audit_date, property_id)
);

--------------------------------------------------------------------------------
-- Triggers: updated_at auto-update
--------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'set_updated_at_housekeeping_tasks') THEN
        CREATE TRIGGER set_updated_at_housekeeping_tasks
            BEFORE UPDATE ON housekeeping_tasks
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'set_updated_at_folios') THEN
        CREATE TRIGGER set_updated_at_folios
            BEFORE UPDATE ON folios
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

COMMIT;
