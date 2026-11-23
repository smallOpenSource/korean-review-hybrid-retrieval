-- ============================================================================
-- Migration 007: Add Composite Indexes for Query Optimization
-- ============================================================================
-- Purpose: Improve performance of frequently used multi-column queries
-- Target: Scheduler pipeline queries + complaint management queries
--
-- Query patterns analyzed:
-- 1. Sync job: WHERE analyzed=1 AND synced_to_opensearch=0 ORDER BY at
-- 2. Analyze job: WHERE analyzed=0 ORDER BY created_at
-- 3. Complaint filters: is_complaint + dept/status/urgency combinations
-- 4. Time-series: package_id + at range queries
--
-- Created: 2025-12-31
-- ============================================================================

-- Index 1: Sync Pipeline Optimization
-- Used by: scheduler/jobs/sync_to_opensearch.py:63-65
-- Query: WHERE synced_to_opensearch = 0 AND analyzed = 1 ORDER BY at DESC
ALTER TABLE reviews
  ADD INDEX idx_sync_pipeline (analyzed, synced_to_opensearch, at);

-- Index 2: Complaint Management by Department
-- Used by: app/services/review_service.py (department filtering + status)
-- Query: WHERE is_complaint=1 AND complaint_primary_dept='X' AND complaint_status='Y'
ALTER TABLE reviews
  ADD INDEX idx_complaint_dept_status (is_complaint, complaint_primary_dept, complaint_status);

-- Index 3: SLA Deadline Monitoring
-- Used by: Complaint monitoring dashboard for overdue complaints
-- Query: WHERE is_complaint=1 AND complaint_sla_deadline < NOW()
ALTER TABLE reviews
  ADD INDEX idx_complaint_sla (is_complaint, complaint_sla_deadline);

-- Index 4: App Timeline Analysis
-- Used by: Review timeline queries per app
-- Query: WHERE package_id='X' AND at BETWEEN 'Y' AND 'Z'
ALTER TABLE reviews
  ADD INDEX idx_app_timeline (package_id, at);

-- Index 5: Complaint Timeline
-- Used by: Complaint trend analysis over time
-- Query: WHERE is_complaint=1 ORDER BY at
ALTER TABLE reviews
  ADD INDEX idx_complaint_timeline (is_complaint, at);

-- Index 6: Monthly Aggregation
-- Used by: scheduler/jobs/aggregate_mart.py:81
-- Query: WHERE YEAR(at)=X AND MONTH(at)=Y
ALTER TABLE reviews
  ADD INDEX idx_year_month_complaint (year, month, is_complaint);

-- Index 7: Complaint Urgency Filtering
-- Used by: app/api/v1/complaints.py:36 (sort by urgency)
-- Query: WHERE is_complaint=1 ORDER BY complaint_urgency, at
ALTER TABLE reviews
  ADD INDEX idx_complaint_urgency_time (is_complaint, complaint_urgency, at);

-- ============================================================================
-- Index Usage Verification Queries
-- ============================================================================
--
-- 1. Check sync pipeline index usage:
--    EXPLAIN SELECT * FROM reviews
--    WHERE analyzed=1 AND synced_to_opensearch=0 ORDER BY at DESC LIMIT 100;
--
-- 2. Check complaint dept index:
--    EXPLAIN SELECT * FROM reviews
--    WHERE is_complaint=1 AND complaint_primary_dept='CS_CENTER'
--    AND complaint_status='new';
--
-- 3. Check SLA monitoring:
--    EXPLAIN SELECT * FROM reviews
--    WHERE is_complaint=1 AND complaint_sla_deadline < NOW();
--
-- 4. View all complaint-related indexes:
--    SHOW INDEX FROM reviews WHERE Key_name LIKE 'idx_%';
--
-- ============================================================================
-- Performance Notes
-- ============================================================================
--
-- - Composite index column order follows selectivity principle:
--   Most selective (filters out most rows) → Least selective → Sort column
--
-- - Index on (analyzed, synced_to_opensearch, at):
--   analyzed filters ~50%, synced filters ~90%, at for sorting
--
-- - Index on (is_complaint, complaint_primary_dept, complaint_status):
--   is_complaint filters ~95%, dept filters ~70%, status for final filter
--
-- - Indexes are created ONLINE in MySQL 8.x (no table lock)
--
-- ============================================================================
-- Rollback Script
-- ============================================================================
--
-- ALTER TABLE reviews
--   DROP INDEX idx_sync_pipeline,
--   DROP INDEX idx_complaint_dept_status,
--   DROP INDEX idx_complaint_sla,
--   DROP INDEX idx_app_timeline,
--   DROP INDEX idx_complaint_timeline,
--   DROP INDEX idx_year_month_complaint,
--   DROP INDEX idx_complaint_urgency_time;
--
-- ============================================================================
