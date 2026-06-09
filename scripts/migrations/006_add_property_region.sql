-- Migration 006: Add region column to properties table
-- Needed for regional manager scoping in PMS reporting.

BEGIN;

ALTER TABLE properties
    ADD COLUMN IF NOT EXISTS region VARCHAR(50);

CREATE INDEX IF NOT EXISTS idx_properties_region ON properties(region);

-- Seed region values for existing properties based on state (best-effort mapping)
UPDATE properties SET region = 'Northeast'
    WHERE state IN ('NY', 'MA', 'CT', 'NJ', 'PA', 'ME', 'NH', 'RI', 'VT') AND region IS NULL;

UPDATE properties SET region = 'Southeast'
    WHERE state IN ('FL', 'GA', 'NC', 'SC', 'VA', 'TN', 'AL', 'MS', 'KY', 'WV', 'DC', 'MD', 'DE') AND region IS NULL;

UPDATE properties SET region = 'Midwest'
    WHERE state IN ('IL', 'IN', 'IA', 'KS', 'MI', 'MN', 'MO', 'NE', 'ND', 'OH', 'SD', 'WI') AND region IS NULL;

UPDATE properties SET region = 'West'
    WHERE state IN ('CA', 'OR', 'WA', 'NV', 'AZ', 'UT', 'CO', 'ID', 'MT', 'WY', 'AK', 'HI', 'NM') AND region IS NULL;

UPDATE properties SET region = 'South'
    WHERE state IN ('TX', 'OK', 'AR', 'LA') AND region IS NULL;

-- Any remaining without matched state: default to 'Other'
UPDATE properties SET region = 'Other' WHERE region IS NULL;

COMMIT;
