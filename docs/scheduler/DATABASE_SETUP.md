# Scheduler Database Configuration Guide

## Environment Variables

Add these environment variables to your `.env` file:

```bash
# ============================================================================
# Scheduler Database Configuration
# ============================================================================

# Database Connection (Required)
SCHEDULER_DB_HOST=127.0.0.1
SCHEDULER_DB_PORT=3306
SCHEDULER_DB_USER=your_mysql_user
SCHEDULER_DB_PASSWORD=<set-in-.env>
SCHEDULER_DB_NAME=app_reviews_scheduler

# Optional: Falls back to MYSQL_USER and MYSQL_PASSWORD if not set
# SCHEDULER_DB_USER=${MYSQL_USER}
# SCHEDULER_DB_PASSWORD=${MYSQL_PASSWORD}

# Database Connection Pool Settings (Optional)
SCHEDULER_DB_POOL_SIZE=5              # Number of connections in pool
SCHEDULER_DB_MAX_OVERFLOW=10          # Max additional connections
SCHEDULER_DB_POOL_TIMEOUT=30          # Seconds to wait for connection
SCHEDULER_DB_POOL_RECYCLE=3600        # Recycle connections after 1 hour
SCHEDULER_DB_CHARSET=utf8mb4
```

## Setup Steps

### 1. Create Database and Tables

```bash
# Login to MySQL/MariaDB
mysql -u your_user -p

# Create database
CREATE DATABASE app_reviews_scheduler 
DEFAULT CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

# Grant permissions
GRANT ALL PRIVILEGES ON app_reviews_scheduler.* TO 'your_user'@'localhost';
FLUSH PRIVILEGES;

# Exit MySQL
EXIT;

# Execute DDL
mysql -u your_user -p app_reviews_scheduler < scheduler/schema/reviews_table.sql
```

### 2. Verify Tables Created

```bash
mysql -u your_user -p app_reviews_scheduler -e "SHOW TABLES;"
```

Expected output:
```
+------------------------------------+
| Tables_in_app_reviews_scheduler    |
+------------------------------------+
| app_metadata                       |
| job_runs                           |
| reviews                            |
+------------------------------------+
```

### 3. Test Database Connection

```bash
cd scheduler
python -c "
from utils.database import get_db_session_factory
factory = get_db_session_factory()
if factory.health_check():
    print('✅ Database connection successful!')
else:
    print('❌ Database connection failed')
"
```

### 4. Run Test Collection

```bash
# Test single app (dry run without DB)
python -m scheduler.main --list-apps

# Test with database (collect high priority apps)
python -m scheduler.main --run-once collect_high
```

## Database Schema Summary

### `reviews` Table
Main table for storing collected reviews with legacy-compatible structure.

**Key Fields:**
- `review_id` (UNIQUE): Play Store review identifier
- `package_id`: App package ID (com.example.app)
- `content`: Original review text
- `original_content`: Preprocessed (special chars preserved)
- `cleaned_content`: NLP-ready (Korean/numbers only)
- `year`, `month`, `day`, `hour`: Time split for queries
- `analyzed`: Flag for integration with main app

**Partitioning:** Year-based (p2023, p2024, p2025, ...)

### `app_metadata` Table
App information from Play Store and configuration.

**Key Fields:**
- `package_id` (PRIMARY): App identifier
- `company_code`, `group_code`: Legacy compatibility
- `title`, `developer`, `genre`: Play Store metadata

### `job_runs` Table
Job execution tracking for monitoring.

**Key Fields:**
- `run_id` (UNIQUE): Job execution identifier
- `job_name`: 'collect_reviews', 'analyze_reviews', etc.
- `status`: 'running', 'completed', 'failed'
- `rows_inserted`, `rows_duplicate`: Statistics

## Troubleshooting

### Connection Errors

**Error:** `Access denied for user`
```bash
# Check MySQL user permissions
mysql -u root -p -e "SELECT User, Host FROM mysql.user WHERE User='your_user';"

# Grant permissions
GRANT ALL PRIVILEGES ON app_reviews_scheduler.* TO 'your_user'@'%';
```

**Error:** `Unknown database`
```bash
# Recreate database
mysql -u root -p -e "CREATE DATABASE app_reviews_scheduler CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### Pool Exhaustion

If you see "QoS exceeded" errors, increase pool size:
```bash
SCHEDULER_DB_POOL_SIZE=10
SCHEDULER_DB_MAX_OVERFLOW=20
```

### Partition Errors

**Error:** `Table has no partition for value XXXX`

Add new partition:
```sql
ALTER TABLE reviews 
ADD PARTITION (PARTITION p2027 VALUES LESS THAN (2028));
```

## Migration from Legacy

If migrating from legacy batch system:

```sql
-- Insert legacy data into new schema
INSERT INTO app_reviews_scheduler.reviews (
    review_id, package_id, content, score, at, year, month, day
)
SELECT 
    reviewid, appid, content, score, at,
    YEAR(at), MONTH(at), DAY(at)
FROM legacy_db.card_f
WHERE NOT EXISTS (
    SELECT 1 FROM app_reviews_scheduler.reviews 
    WHERE review_id = legacy_db.card_f.reviewid
);
```

## Monitoring Queries

### Check Recent Job Runs
```sql
SELECT job_name, package_id, status, 
       rows_inserted, rows_duplicate,
       started_at, completed_at
FROM job_runs
ORDER BY started_at DESC
LIMIT 10;
```

### Review Collection Stats
```sql
SELECT 
    package_id,
    COUNT(*) as total_reviews,
    COUNT(DISTINCT DATE(at)) as days_covered,
    MIN(at) as earliest_review,
    MAX(at) as latest_review
FROM reviews
GROUP BY package_id;
```

### Partition Distribution
```sql
SELECT 
    PARTITION_NAME,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = 'app_reviews_scheduler'
  AND TABLE_NAME = 'reviews';
```
