-- Rollback Migration 003: PMS Schema Extension
-- Reverses all changes from 003_pms_schema.sql

BEGIN;

-- Drop new tables (order matters due to FK constraints)
DROP TABLE IF EXISTS night_audit_runs CASCADE;
DROP TABLE IF EXISTS loyalty_transactions CASCADE;
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS charges CASCADE;
DROP TABLE IF EXISTS folios CASCADE;
DROP TABLE IF EXISTS housekeeping_tasks CASCADE;
DROP TABLE IF EXISTS checkinout_records CASCADE;

-- Remove added columns from guests
ALTER TABLE guests
    DROP COLUMN IF EXISTS loyalty_tier,
    DROP COLUMN IF EXISTS total_stays,
    DROP COLUMN IF EXISTS points_balance,
    DROP COLUMN IF EXISTS lifetime_points_earned;

-- Remove added columns from reservations
ALTER TABLE reservations
    DROP COLUMN IF EXISTS lifecycle_execution_arn,
    DROP COLUMN IF EXISTS check_in_task_token,
    DROP COLUMN IF EXISTS check_out_task_token,
    DROP COLUMN IF EXISTS checked_in_at,
    DROP COLUMN IF EXISTS checked_out_at;

COMMIT;
