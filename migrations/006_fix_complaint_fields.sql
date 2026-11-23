-- ============================================================================
-- Migration 006: Fix Complaint Field Naming Consistency
-- ============================================================================
-- Purpose: Resolve MySQL ↔ OpenSearch field name mismatches
-- Issue: MySQL's complaint_dept maps to OpenSearch's complaint.primary_dept
--        but queries use complaint.escalated_to (different meaning)
-- Solution: Rename MySQL column + add missing fields
--
-- References:
-- - docs/todo/critical/04_schema_consistency.md
-- - scheduler/jobs/sync_to_opensearch.py:112
-- - app/services/review_service.py:795,1022
--
-- Created: 2025-12-31
-- ============================================================================

-- Step 1: Rename complaint_dept to complaint_primary_dept
-- Uses CHANGE COLUMN for online ALTER (no table lock in MySQL 8.x)
ALTER TABLE reviews
  CHANGE COLUMN complaint_dept complaint_primary_dept VARCHAR(50)
  COMMENT '민원 1차 담당 부서 (primary department for complaint)';

-- Step 2: Add new complaint-related columns
ALTER TABLE reviews
  ADD COLUMN complaint_sla_deadline DATETIME NULL
    COMMENT 'SLA 마감 시간 (calculated from urgency)',
  ADD COLUMN complaint_assigned_to VARCHAR(100) NULL
    COMMENT '민원 담당자 이름 또는 ID (assigned person)',
  ADD COLUMN complaint_escalated_to VARCHAR(50) NULL
    COMMENT '에스컬레이션된 부서 (escalated department, may differ from primary_dept)';

-- Step 3: Add indexes for query performance
-- Note: Only index fields likely to be used in WHERE/ORDER BY clauses
ALTER TABLE reviews
  ADD INDEX idx_complaint_assigned_to (complaint_assigned_to),
  ADD INDEX idx_complaint_sla_deadline (complaint_sla_deadline);

-- Step 4: Migrate existing data
-- Set initial escalated_to = primary_dept for existing complaints
UPDATE reviews
SET complaint_escalated_to = complaint_primary_dept
WHERE is_complaint = 1
  AND complaint_primary_dept IS NOT NULL
  AND complaint_escalated_to IS NULL;

-- Step 5: Calculate SLA deadlines for existing complaints
-- Based on urgency level (critical: 4h, high: 1d, medium: 3d, low: 7d)
UPDATE reviews
SET complaint_sla_deadline = CASE complaint_urgency
  WHEN 'critical' THEN DATE_ADD(created_at, INTERVAL 4 HOUR)
  WHEN 'high' THEN DATE_ADD(created_at, INTERVAL 1 DAY)
  WHEN 'medium' THEN DATE_ADD(created_at, INTERVAL 3 DAY)
  WHEN 'low' THEN DATE_ADD(created_at, INTERVAL 7 DAY)
  ELSE DATE_ADD(created_at, INTERVAL 7 DAY)
END
WHERE is_complaint = 1
  AND complaint_urgency IS NOT NULL
  AND complaint_sla_deadline IS NULL;

-- ============================================================================
-- Verification Queries (Run manually after migration)
-- ============================================================================
--
-- 1. Check column rename:
--    SELECT complaint_primary_dept FROM reviews WHERE is_complaint = 1 LIMIT 10;
--
-- 2. Verify new columns exist:
--    DESCRIBE reviews;
--
-- 3. Check data migration:
--    SELECT review_id, complaint_primary_dept, complaint_escalated_to,
--           complaint_sla_deadline, complaint_urgency
--    FROM reviews
--    WHERE is_complaint = 1
--    LIMIT 10;
--
-- 4. Verify indexes:
--    SHOW INDEX FROM reviews WHERE Key_name LIKE 'idx_complaint%';
--
-- ============================================================================
-- Rollback Script (if needed)
-- ============================================================================
--
-- ALTER TABLE reviews
--   CHANGE COLUMN complaint_primary_dept complaint_dept VARCHAR(50);
--
-- ALTER TABLE reviews
--   DROP INDEX idx_complaint_assigned_to,
--   DROP INDEX idx_complaint_sla_deadline,
--   DROP COLUMN complaint_sla_deadline,
--   DROP COLUMN complaint_assigned_to,
--   DROP COLUMN complaint_escalated_to;
--
-- ============================================================================
