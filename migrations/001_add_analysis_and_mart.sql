-- Add analysis columns to reviews table
ALTER TABLE reviews
ADD COLUMN IF NOT EXISTS category_primary VARCHAR(50),
ADD COLUMN IF NOT EXISTS category_secondary TEXT,
ADD COLUMN IF NOT EXISTS category_confidence FLOAT,
ADD COLUMN IF NOT EXISTS sentiment_emotions TEXT,
ADD COLUMN IF NOT EXISTS sentiment_confidence FLOAT,
ADD COLUMN IF NOT EXISTS complaint_sub_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS complaint_severity INT,
ADD COLUMN IF NOT EXISTS complaint_secondary_depts TEXT,
ADD COLUMN IF NOT EXISTS complaint_escalation_required BOOLEAN DEFAULT 0,
ADD COLUMN IF NOT EXISTS complaint_escalation_level VARCHAR(20),
ADD COLUMN IF NOT EXISTS complaint_status VARCHAR(20) DEFAULT 'new',
ADD COLUMN IF NOT EXISTS reasoning JSON;

-- Create Mart Table: App Stats Monthly
CREATE TABLE IF NOT EXISTS mart_app_stats_monthly (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    app_id VARCHAR(50) NOT NULL,
    year INT NOT NULL,
    month INT NOT NULL,
    total_reviews INT DEFAULT 0,
    avg_rating FLOAT DEFAULT 0,
    avg_sentiment_score FLOAT DEFAULT 0,
    positive_count INT DEFAULT 0,
    negative_count INT DEFAULT 0,
    complaint_count INT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_app_ym (app_id, year, month)
);

-- Create Mart Table: Dept Stats Monthly
CREATE TABLE IF NOT EXISTS mart_dept_stats_monthly (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    dept_code VARCHAR(50) NOT NULL,
    year INT NOT NULL,
    month INT NOT NULL,
    total_assigned INT DEFAULT 0,
    avg_urgency FLOAT DEFAULT 0,
    avg_severity FLOAT DEFAULT 0,
    status_new INT DEFAULT 0,
    status_in_progress INT DEFAULT 0,
    status_resolved INT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_dept_ym (dept_code, year, month)
);
