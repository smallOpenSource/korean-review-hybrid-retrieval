-- DDL for Issue #4: MySQL-OpenSearch Sync Tracking
-- Execute this on app_reviews_scheduler database

USE app_reviews_scheduler;

-- Add sync tracking columns to reviews table
ALTER TABLE reviews 
ADD COLUMN IF NOT EXISTS synced_to_opensearch BOOLEAN DEFAULT FALSE COMMENT 'OpenSearch sync status',
ADD COLUMN IF NOT EXISTS synced_at TIMESTAMP NULL COMMENT 'Last synced timestamp';

-- Add index for efficient querying of unsynced reviews
CREATE INDEX IF NOT EXISTS idx_sync_status ON reviews(synced_to_opensearch, created_at);

-- Verify columns added
SHOW COLUMNS FROM reviews LIKE 'synced%';

-- Check current unsynced count
SELECT COUNT(*) as unsynced_count FROM reviews WHERE synced_to_opensearch = FALSE;
