-- Mart table for Dept Review filter counts
-- This table stores pre-aggregated counts for fast filter badge display
CREATE TABLE IF NOT EXISTS mart_dept_review_filter_counts (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    app_id VARCHAR(255) NOT NULL COMMENT 'Package ID of the app',
    dept_code VARCHAR(50) NOT NULL COMMENT 'Department code',
    review_count INT NOT NULL DEFAULT 0 COMMENT 'Total complaint reviews',
    last_30_days_count INT NOT NULL DEFAULT 0 COMMENT 'Reviews in last 30 days',
    last_updated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last aggregation time',
    UNIQUE KEY uk_app_dept (app_id, dept_code),
    INDEX idx_dept (dept_code),
    INDEX idx_app (app_id),
    INDEX idx_updated (last_updated)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Pre-aggregated filter counts for Dept Review page';
