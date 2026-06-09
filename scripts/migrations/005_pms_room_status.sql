-- Migration 005: Expand rooms.status check constraint to support PMS statuses
-- Adds AVAILABLE, OCCUPIED, CLEANING, INSPECTING (PMS operational states)
-- Keeps existing CRS statuses: CLEAN, DIRTY, INSPECTED, OUT_OF_ORDER, OUT_OF_INVENTORY

BEGIN;

-- Drop old constraint
ALTER TABLE rooms DROP CONSTRAINT IF EXISTS rooms_status_check;

-- Add new constraint with expanded status values
ALTER TABLE rooms ADD CONSTRAINT rooms_status_check
    CHECK (status IN (
        -- CRS original statuses
        'CLEAN', 'DIRTY', 'INSPECTED', 'OUT_OF_ORDER', 'OUT_OF_INVENTORY',
        -- PMS operational statuses
        'AVAILABLE', 'OCCUPIED', 'CLEANING', 'INSPECTING'
    ));

-- Migrate existing CLEAN rooms to AVAILABLE (they mean the same thing in PMS context)
UPDATE rooms SET status = 'AVAILABLE' WHERE status = 'CLEAN';

COMMIT;
