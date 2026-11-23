-- =============================================================================
-- Rollback Script for Department Routing Tables
-- =============================================================================
-- Purpose: DB 마이그레이션 롤백용
-- Usage: mysql -u$USER -p$PASS -h$HOST $DB < rollback_routing_tables.sql
-- =============================================================================

USE app_reviews_scheduler;

-- 외래 키 제약 때문에 역순으로 삭제
DROP TABLE IF EXISTS routing_keywords;
DROP TABLE IF EXISTS routing_sentences;
DROP TABLE IF EXISTS routing_collaboration_rules;
DROP TABLE IF EXISTS routing_escalation_rules;
DROP TABLE IF EXISTS routing_teams;
DROP TABLE IF EXISTS routing_divisions;

-- 롤백 완료
SELECT 'Rollback completed. All routing tables dropped.' AS status;
