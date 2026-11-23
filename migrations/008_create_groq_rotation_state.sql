-- =============================================================================
-- Migration 008: Create Groq Rotation State Table
-- =============================================================================
-- Purpose: Track current Groq API key index for 5-key rotation
-- Author: Claude Code
-- Date: 2026-01-04
-- =============================================================================

CREATE TABLE IF NOT EXISTS `groq_rotation_state` (
  `id` INT PRIMARY KEY DEFAULT 1 COMMENT 'Singleton row (always 1)',
  `current_key_index` INT NOT NULL DEFAULT 0 COMMENT 'Current Groq key index (0-4)',
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last rotation time',
  CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Groq API key rotation state';

-- Initialize with key index 0
INSERT INTO `groq_rotation_state` (id, current_key_index)
VALUES (1, 0)
ON DUPLICATE KEY UPDATE id=id;

-- Verify table created
SELECT 'groq_rotation_state table created successfully' AS status;
SELECT * FROM `groq_rotation_state`;
