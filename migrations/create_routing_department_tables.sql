-- =============================================================================
-- Department Routing Tables for AI-based Routing System
-- =============================================================================
-- Target Database: app_reviews_scheduler
-- Purpose: AI 기반 부서 라우팅 (YAML 대체)
-- Features: Embedding vector storage, keyword matching, collaboration rules
-- =============================================================================

USE app_reviews_scheduler;

-- -----------------------------------------------------------------------------
-- 1. Divisions (본부)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS routing_divisions (
    division_code VARCHAR(50) PRIMARY KEY COMMENT '본부 코드 (예: DIGITAL_CHANNEL)',
    name VARCHAR(100) NOT NULL COMMENT '본부명',
    description TEXT COMMENT '본부 설명',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='부서 라우팅용 본부 정보';

-- -----------------------------------------------------------------------------
-- 2. Teams (팀)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS routing_teams (
    team_id INT AUTO_INCREMENT PRIMARY KEY,
    team_code VARCHAR(50) NOT NULL COMMENT '팀 코드 (예: MOBILE_BANKING)',
    division_code VARCHAR(50) NOT NULL COMMENT '본부 코드',
    name VARCHAR(100) NOT NULL COMMENT '팀명',
    description TEXT COMMENT '팀 설명',
    embedding_vector TEXT COMMENT 'JSON array: 1024-dim BGE-M3 embedding',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_team (division_code, team_code),
    FOREIGN KEY (division_code) REFERENCES routing_divisions(division_code) ON DELETE CASCADE,
    INDEX idx_division (division_code),
    INDEX idx_team_code (team_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='부서 라우팅용 팀 정보 (embedding 포함)';

-- -----------------------------------------------------------------------------
-- 3. Keywords (키워드)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS routing_keywords (
    keyword_id INT AUTO_INCREMENT PRIMARY KEY,
    team_id INT NOT NULL,
    keyword VARCHAR(100) NOT NULL COMMENT '라우팅 키워드',
    weight DECIMAL(3, 2) DEFAULT 1.0 COMMENT 'TF-IDF 가중치',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES routing_teams(team_id) ON DELETE CASCADE,
    INDEX idx_keyword (keyword),
    INDEX idx_team (team_id),
    INDEX idx_keyword_team (keyword, team_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='팀별 라우팅 키워드';

-- -----------------------------------------------------------------------------
-- 4. Representative Sentences (대표 문장)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS routing_sentences (
    sentence_id INT AUTO_INCREMENT PRIMARY KEY,
    team_id INT NOT NULL,
    sentence TEXT NOT NULL COMMENT '대표 문장 (embedding 생성용)',
    priority INT DEFAULT 1 COMMENT '우선순위 (1-5, 낮을수록 우선)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES routing_teams(team_id) ON DELETE CASCADE,
    INDEX idx_team_priority (team_id, priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='팀별 대표 문장';

-- -----------------------------------------------------------------------------
-- 5. Collaboration Rules (협업 규칙)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS routing_collaboration_rules (
    rule_id INT AUTO_INCREMENT PRIMARY KEY,
    rule_name VARCHAR(100) NOT NULL,
    trigger_keywords TEXT COMMENT 'JSON array: 트리거 키워드 목록',
    primary_division VARCHAR(50) COMMENT '주 담당 본부',
    primary_team VARCHAR(50) COMMENT '주 담당 팀',
    secondary_depts TEXT COMMENT 'JSON array: [{division, team, role}]',
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='부서 협업 규칙';

-- -----------------------------------------------------------------------------
-- 6. Escalation Rules (에스컬레이션 규칙)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS routing_escalation_rules (
    rule_id INT AUTO_INCREMENT PRIMARY KEY,
    rule_name VARCHAR(100) NOT NULL,
    keywords TEXT COMMENT 'JSON array: 트리거 키워드 목록',
    urgency INT DEFAULT 1 COMMENT '긴급도 (1-5)',
    escalation_level VARCHAR(50) COMMENT 'staff/manager/director/executive',
    sla_hours INT DEFAULT 168 COMMENT 'SLA 시간 (기본 7일)',
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='에스컬레이션 규칙';

-- =============================================================================
-- 테이블 생성 완료
-- =============================================================================
-- 다음 단계: python scripts/migrate_yaml_to_db.py 실행
-- =============================================================================
