-- ============================================================================
-- AnyCompany Hotel CRS — Migration 002: Integration Fields
-- Adds columns to support PMS integration (reverse bridge status updates)
-- ============================================================================

ALTER TABLE reservations ADD COLUMN IF NOT EXISTS pms_reservation_id VARCHAR;
ALTER TABLE reservations ADD COLUMN IF NOT EXISTS checked_in_at TIMESTAMPTZ;
ALTER TABLE reservations ADD COLUMN IF NOT EXISTS checked_out_at TIMESTAMPTZ;
ALTER TABLE reservations ADD COLUMN IF NOT EXISTS pms_folio_total NUMERIC(10,2);
ALTER TABLE reservations ADD COLUMN IF NOT EXISTS pms_sync_status VARCHAR(20);

CREATE INDEX IF NOT EXISTS idx_reservations_pms_sync
    ON reservations(pms_sync_status) WHERE pms_sync_status IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reservations_pms_reservation
    ON reservations(pms_reservation_id) WHERE pms_reservation_id IS NOT NULL;

-- ============================================================================
-- End of migration 002
-- ============================================================================
