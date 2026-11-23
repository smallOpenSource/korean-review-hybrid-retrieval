-- Create Gemini API and Model rotation state table
-- This table stores the current rotation state for both API keys and models

CREATE TABLE IF NOT EXISTS `gemini_rotation_state` (
  `id` INT PRIMARY KEY DEFAULT 1 COMMENT 'Singleton row - only one record allowed',
  `current_key_index` INT NOT NULL DEFAULT 0 COMMENT 'Current API key index (0-based)',
  `current_model_index` INT NOT NULL DEFAULT 0 COMMENT 'Current model index (0-based)',
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update time',
  CHECK (id = 1) -- Ensure only one row exists
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Gemini API key and model rotation state';

-- Initialize with defaults (key index 0, model index 0)
INSERT INTO `gemini_rotation_state` (id, current_key_index, current_model_index)
VALUES (1, 0, 0)
ON DUPLICATE KEY UPDATE id=id;
