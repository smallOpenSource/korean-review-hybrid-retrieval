-- Reviews Table DDL for Scheduler
-- Implements legacy batch table structure with improvements
-- Based on the legacy batch DDL (not included in this public copy)

CREATE DATABASE IF NOT EXISTS app_reviews_scheduler 
DEFAULT CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

USE app_reviews_scheduler;

-- Main reviews table with legacy-compatible structure
CREATE TABLE IF NOT EXISTS reviews (
  -- Primary key
  id BIGINT AUTO_INCREMENT,
  
  -- Review identification (from Play Store)
  review_id VARCHAR(255) NOT NULL,
  package_id VARCHAR(255) NOT NULL,
  
  -- User information
  user_name VARCHAR(255),
  user_image TEXT,
  
  -- Content fields (legacy preprocessing applied)
  content TEXT NOT NULL,                    -- Original from Play Store
  original_content TEXT,                    -- Human-readable (special chars preserved)
  cleaned_content TEXT,                     -- For NLP (Korean/numbers only)
  
  -- Rating and metadata
  score FLOAT DEFAULT 0,
  thumbs_up_count INT DEFAULT 0,
  review_created_version VARCHAR(255),
  
  -- Timestamps
  at DATETIME NOT NULL,                     -- Review creation time
  replied_at DATETIME,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  -- Developer response
  reply_content TEXT,
  
  -- Additional metadata
  app_version VARCHAR(255),
  content_hash VARCHAR(32),
  
  -- Time split fields (from legacy dataLoad.py)
  year INT,
  month INT,
  day INT,
  hour INT,
  
  -- Analysis flags (for integration with main app)
  analyzed BOOLEAN DEFAULT FALSE,
  analysis_failed BOOLEAN DEFAULT FALSE,
  
  -- OpenSearch sync tracking (Issue #4 resolution)
  synced_to_opensearch BOOLEAN DEFAULT FALSE,
  synced_at TIMESTAMP NULL,
  
  -- Indexes
  PRIMARY KEY (id, at),
  -- Note: review_id uniqueness is enforced at application level (see collect_reviews.py)
  -- Cannot use UNIQUE KEY here due to partitioning constraints (must include 'at' column)
  KEY idx_review_id (review_id),
  KEY idx_package_id (package_id),
  KEY idx_review_time (at),
  KEY idx_year_month (year, month),
  KEY idx_score (score),
  KEY idx_analyzed (analyzed),
  KEY idx_content_hash (content_hash)
  
) ENGINE=InnoDB 
  DEFAULT CHARSET=utf8mb4 
  COLLATE=utf8mb4_unicode_ci
  ROW_FORMAT=COMPRESSED
  -- Year-based partitioning using YEAR() function (from legacy structure)
  PARTITION BY RANGE (YEAR(at)) (
    PARTITION p2023 VALUES LESS THAN (2024),
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION pmax VALUES LESS THAN MAXVALUE
  );

-- App metadata table (compatible with legacy summary.dict)
CREATE TABLE IF NOT EXISTS app_metadata (
  package_id VARCHAR(255) PRIMARY KEY,
  company_code VARCHAR(50),
  group_code VARCHAR(50),
  company_name VARCHAR(255),
  category VARCHAR(50),
  priority VARCHAR(20),
  
  -- App info from Play Store
  title VARCHAR(255),
  developer VARCHAR(255),
  genre VARCHAR(100),
  score FLOAT,
  ratings INT,
  installs VARCHAR(50),
  
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  KEY idx_category (category),
  KEY idx_priority (priority),
  KEY idx_company_code (company_code)
) ENGINE=InnoDB 
  DEFAULT CHARSET=utf8mb4 
  COLLATE=utf8mb4_unicode_ci;

-- Job execution tracking
CREATE TABLE IF NOT EXISTS job_runs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  job_name VARCHAR(100) NOT NULL,
  run_id VARCHAR(100) NOT NULL,
  package_id VARCHAR(255),
  status VARCHAR(20) NOT NULL,              -- 'running', 'completed', 'failed'
  
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP NULL,
  
  rows_inserted INT DEFAULT 0,
  rows_duplicate INT DEFAULT 0,
  error_message TEXT,
  
  UNIQUE KEY uk_run_id (run_id),
  KEY idx_job_package (job_name, package_id),
  KEY idx_status (status),
  KEY idx_started_at (started_at)
) ENGINE=InnoDB 
  DEFAULT CHARSET=utf8mb4 
  COLLATE=utf8mb4_unicode_ci;
