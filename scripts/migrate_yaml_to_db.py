#!/usr/bin/env python
"""
YAML 부서 계층 구조를 MariaDB로 마이그레이션

파일: scripts/migrate_yaml_to_db.py
용도: department_hierarchy.yaml → routing_* 테이블
"""
import asyncio
import yaml
import json
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.mysql_client import MySQLClient
from app.agents.embedding_service import get_embedding_service
import pymysql.cursors

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

CONFIG_DIR = project_root / "app" / "config"


async def migrate_hierarchy():
    """YAML → DB 마이그레이션 (비동기)"""
    logger.info("="*80)
    logger.info("Starting YAML → DB Migration")
    logger.info("="*80)
    
    # 1. YAML 로드
    yaml_path = CONFIG_DIR / "department_hierarchy.yaml"
    if not yaml_path.exists():
        logger.error(f"YAML file not found: {yaml_path}")
        return False
    
    logger.info(f"Loading YAML from {yaml_path}")
    with open(yaml_path, 'r', encoding='utf-8') as f:
        hierarchy = yaml.safe_load(f)
    
    mysql = MySQLClient()
    embed_service = get_embedding_service()
    
    try:
        with mysql.get_connection() as conn:
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("BEGIN")
            
            logger.info("✓ Connection established, starting transaction")
            
            # 3. Divisions
            divisions = hierarchy.get('divisions', {})
            logger.info(f"\n[Step 1/6] Migrating {len(divisions)} divisions...")
            
            for div_code, div_data in divisions.items():
                cursor.execute(
                    """INSERT INTO routing_divisions (division_code, name, description) 
                       VALUES (%s, %s, %s) 
                       ON DUPLICATE KEY UPDATE name=VALUES(name), description=VALUES(description)""",
                    (div_code, div_data.get('name'), div_data.get('description', ''))
                )
                logger.info(f"  ✓ {div_code}")
            
            # 4. Teams 데이터 수집
            logger.info(f"\n[Step 2/6] Collecting team data...")
            teams_data = []
            
            for div_code, div_data in divisions.items():
                for team_code, team_data in div_data.get('teams', {}).items():
                    teams_data.append({
                        'team_code': team_code,
                        'division_code': div_code,
                        'name': team_data.get('name'),
                        'description': team_data.get('description', ''),
                        'keywords': team_data.get('keywords', []),
                        'sentences': team_data.get('representative_sentences', [])
                    })
            
            logger.info(f"  ✓ Collected {len(teams_data)} teams")
            
            # 5. Teams + Embedding
            logger.info(f"\n[Step 3/6] Migrating teams and generating embeddings...")
            embed_ok = 0
            embed_fail = 0
            
            for idx, td in enumerate(teams_data, 1):
                full_code = f"{td['division_code']}.{td['team_code']}"
                logger.info(f"  [{idx}/{len(teams_data)}] {full_code}")
                
                cursor.execute(
                    """INSERT INTO routing_teams (team_code, division_code, name, description) 
                       VALUES (%s, %s, %s, %s) 
                       ON DUPLICATE KEY UPDATE name=VALUES(name)""",
                    (td['team_code'], td['division_code'], td['name'], td['description'])
                )
                
                cursor.execute(
                    "SELECT team_id FROM routing_teams WHERE team_code = %s AND division_code = %s",
                    (td['team_code'], td['division_code'])
                )
                team_id = cursor.fetchone()['team_id']
                
                # Embedding
                if td['sentences']:
                    try:
                        text = " ".join(td['sentences'][:5])
                        embed_result = await embed_service.embed(text)
                        embed_json = json.dumps(embed_result.embedding, ensure_ascii=False)
                        cursor.execute(
                            "UPDATE routing_teams SET embedding_vector = %s WHERE team_id = %s",
                            (embed_json, team_id)
                        )
                        embed_ok += 1
                        logger.info(f"    ✓ Embedding")
                    except Exception as e:
                        embed_fail += 1
                        logger.warning(f"    ✗ Embedding: {e}")
                
                # Keywords
                if td['keywords']:
                    cursor.executemany(
                        "INSERT INTO routing_keywords (team_id, keyword) VALUES (%s, %s)",
                        [(team_id, kw) for kw in td['keywords']]
                    )
                    logger.info(f"    ✓ {len(td['keywords'])} keywords")
                
                # Sentences
                if td['sentences']:
                    cursor.executemany(
                        "INSERT INTO routing_sentences (team_id, sentence, priority) VALUES (%s, %s, %s)",
                        [(team_id, sent, pri) for pri, sent in enumerate(td['sentences'], 1)]
                    )
                    logger.info(f"    ✓ {len(td['sentences'])} sentences")
            
            logger.info(f"\n  Embeddings: {embed_ok} ok, {embed_fail} failed")
            
            # 6. Collaboration
            logger.info(f"\n[Step 4/6] Collaboration rules...")
            collab = hierarchy.get('collaboration_rules', [])
            for idx, rule in enumerate(collab, 1):
                cursor.execute(
                    """INSERT INTO routing_collaboration_rules 
                       (rule_name, trigger_keywords, secondary_depts, description) 
                       VALUES (%s, %s, %s, %s)""",
                    (rule.get('name', f'rule_{idx}'),
                     json.dumps(rule.get('trigger_keywords', []), ensure_ascii=False),
                     json.dumps(rule.get('secondary', []), ensure_ascii=False),
                     rule.get('description', ''))
                )
            logger.info(f"  ✓ {len(collab)} rules")
            
            # 7. Escalation
            logger.info(f"\n[Step 5/6] Escalation rules...")
            esc = hierarchy.get('escalation_rules', {})
            for name, data in esc.items():
                cursor.execute(
                    """INSERT INTO routing_escalation_rules 
                       (rule_name, keywords, urgency, escalation_level, sla_hours, description) 
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (name,
                     json.dumps(data.get('keywords', []), ensure_ascii=False),
                     data.get('urgency', 1),
                     data.get('escalation_level', 'staff'),
                     data.get('sla_hours', 168),
                     data.get('description', ''))
                )
            logger.info(f"  ✓ {len(esc)} rules")
            
            # 8. Commit
            logger.info(f"\n[Step 6/6] Committing...")
            conn.commit()
            logger.info("  ✓ Committed")
            
            # Stats
            cursor.execute("SELECT COUNT(*) as cnt FROM routing_teams")
            teams_cnt = cursor.fetchone()['cnt']
            cursor.execute("SELECT COUNT(*) as cnt FROM routing_teams WHERE embedding_vector IS NOT NULL")
            embed_cnt = cursor.fetchone()['cnt']
            
            logger.info("\n" + "="*80)
            logger.info(f"✅ Migration Success!")
            logger.info(f"   Teams: {teams_cnt}, Embeddings: {embed_cnt}/{teams_cnt}")
            logger.info("="*80)
            
            cursor.close()
        
        return True
        
    except Exception as e:
        logger.error(f"\n❌ Failed: {e}")
        logger.exception("Traceback:")
        return False


def main():
    """메인"""
    try:
        success = asyncio.run(migrate_hierarchy())
        if success:
            logger.info("\nNext: Verify with SELECT * FROM routing_teams LIMIT 5;")
            sys.exit(0)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("\nInterrupted")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\nError: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
