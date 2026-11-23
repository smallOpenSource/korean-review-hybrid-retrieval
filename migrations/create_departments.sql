-- Department Management Tables
-- Created: 2025-11-27

-- 1. Departments Table (supports hierarchy)
CREATE TABLE IF NOT EXISTS departments (
    dept_code VARCHAR(50) PRIMARY KEY COMMENT '부서 코드',
    dept_name VARCHAR(100) NOT NULL COMMENT '부서명',
    dept_name_en VARCHAR(100) COMMENT '부서명(영문)',
    parent_dept_code VARCHAR(50) COMMENT '상위 부서 코드',
    display_order INT DEFAULT 0 COMMENT '표시 순서',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성 일시',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 일시',
    FOREIGN KEY (parent_dept_code) REFERENCES departments(dept_code) ON DELETE SET NULL,
    INDEX idx_parent (parent_dept_code),
    INDEX idx_order (display_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='부서 정보 테이블';

-- 2. App-Department Mapping Table (N:M relationship)
CREATE TABLE IF NOT EXISTS app_department_mapping (
    package_id VARCHAR(255) COMMENT '앱 패키지 ID',
    dept_code VARCHAR(50) COMMENT '부서 코드',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '매핑 생성 일시',
    PRIMARY KEY (package_id, dept_code),
    FOREIGN KEY (package_id) REFERENCES app_metadata(package_id) ON DELETE CASCADE,
    FOREIGN KEY (dept_code) REFERENCES departments(dept_code) ON DELETE CASCADE,
    INDEX idx_dept (dept_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='앱-부서 매핑 테이블';
