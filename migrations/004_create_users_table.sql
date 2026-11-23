-- Migration 004: Create users table for JWT authentication
-- Created: 2025-12-31
-- Purpose: Implement API authentication system with JWT and API Key support

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    roles JSON NOT NULL COMMENT 'Array of roles: admin, analyst, viewer',
    is_active BOOLEAN DEFAULT TRUE,
    api_key VARCHAR(64) UNIQUE COMMENT 'API key for external integrations',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_username (username),
    INDEX idx_email (email),
    INDEX idx_api_key (api_key),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Initial users are NOT seeded here (no default passwords in the public repo).
-- Create the first admin account with environment variables:
--   ADMIN_USERNAME=admin ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD='<strong password>' \
--     python scripts/create_user.py --roles admin
