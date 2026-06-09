-- Migration 004: Add room_id column to reservations
-- This column tracks the specific room assigned at check-in (was missed in 003)
-- room_id is nullable — it's populated only when a reservation is checked in or pre-assigned

BEGIN;

ALTER TABLE reservations
    ADD COLUMN IF NOT EXISTS room_id UUID REFERENCES rooms(room_id);

CREATE INDEX IF NOT EXISTS idx_reservations_room_id ON reservations(room_id) WHERE room_id IS NOT NULL;

COMMIT;
