import logging
import sys
from pathlib import Path
from sqlalchemy import text

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scheduler.utils.database import get_db_session

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import yaml
import json

def load_apps_from_config():
    config_path = project_root / 'scheduler' / 'config' / 'apps_config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Slug mapping for known apps to ensure clean URLs
    SLUG_MAPPING = {
        'com.example.pay_e': 'pay_e',
        'com.example.bank_l': 'bank_l',
        'com.example.bank_k': 'bank_k',
        'com.example.bank_m': 'bank_m',
        'com.example.bank_c': 'bank_c',
        'com.example.bank_b': 'bank_b',
        'com.example.bank_a': 'bank_a',
        'com.example.bank_d': 'bank_d',
        'com.example.bank_e': 'bank_e',
        'com.example.bank_f': 'bank_f',
        'com.example.bank_g': 'bank_g',
        'com.example.bank_h': 'bank_h',
        'com.example.bank_i': 'bank_i',
        'com.example.bank_j': 'bank_j',
        'com.example.bank_n': 'bank_n',
        'com.example.bank_o': 'bank_o',
        'com.example.bank_p': 'bank_p',
        'com.example.bank_q': 'bank_q',
        'com.example.bank_r': 'bank_r',
        'com.example.bank_s': 'bank_s',
        'com.example.bank_t': 'bank_t',
        'com.example.sec_a': 'sec_a',
        'com.example.sec_b': 'sec_b',
        'com.example.sec_c': 'sec_c',
        'com.example.sec_d': 'sec_d',
        'com.example.sec_e': 'sec_e',
        'com.example.sec_f': 'sec_f',
        'com.example.sec_g': 'sec_g',
        'com.example.sec_h': 'sec_h',
        'com.example.sec_i': 'sec_i',
        'com.example.sec_j': 'sec_j',
        'com.example.sec_k': 'sec_k',
        'com.example.sec_l': 'sec_l',
        'com.example.sec_m': 'sec_m',
        'com.example.sec_n': 'sec_n',
        'com.example.card_a': 'card_a',
        'com.example.card_b': 'card_b',
        'com.example.card_c': 'card_c',
        'com.example.card_d': 'card_d',
        'com.example.card_e': 'card_e',
        'com.example.card_f': 'card_f',
        'com.example.card_g': 'card_g',
        'com.example.card_h': 'card_h',
        'com.example.card_i': 'card_i',
        'com.example.life_a': 'life_a',
        'com.example.life_b': 'life_b',
        'com.example.life_c': 'life_c',
        'com.example.life_d': 'life_d',
        'com.example.life_e': 'life_e',
        'com.example.life_f': 'tongyang',
        'com.example.life_g': 'life_g',
        'com.example.life_h': 'life_h',
        'com.example.life_i': 'life_i',
        'com.example.ins_a': 'ins_a',
        'com.example.ins_b': 'ins_b',
        'com.example.ins_c': 'ins_c',
        'com.example.ins_d': 'ins_d',
        'com.example.ins_e': 'ins_e',
        'com.example.ins_f': 'ins_f',
        'com.example.ins_g': 'ins_g',
        'com.example.ins_h': 'ins_h',
        'com.example.pay_a': 'pay_a',
        'com.example.pay_b': 'pay_b',
        'com.example.pay_c': 'pay_c',
        'com.example.pay_d': 'pay_d',
        'com.example.pay_e': 'pay_e',
        'com.example.pay_f': 'pay_f',
        'com.example.pay_g': 'pay_g',
        'com.example.pay_h': 'pay_h'
    }

    # Build legacy_ids mapping from app_id_history
    legacy_ids_map = {}
    for history_entry in config.get('app_id_history', []):
        current_id = history_entry.get('current')
        previous_ids = [p.get('id') for p in history_entry.get('previous', []) if p.get('id')]
        if current_id and previous_ids:
            legacy_ids_map[current_id] = previous_ids
    
    logger.info(f"Loaded {len(legacy_ids_map)} apps with legacy IDs from app_id_history")
    
    apps = []
    for category_key, category_data in config.get('categories', {}).items():
        for app in category_data.get('apps', []):
            # Add category info to app
            app['group'] = category_key
            
            # Use mapped slug if available, otherwise fallback to package name split
            package_id = app['package_id']
            if package_id in SLUG_MAPPING:
                app['code'] = SLUG_MAPPING[package_id]
            else:
                # Fallback: try to find a meaningful part
                parts = package_id.split('.')
                if len(parts) > 1:
                    app['code'] = parts[-1]
                else:
                    app['code'] = package_id
            
            # Add legacy_ids from app_id_history
            app['legacy_ids'] = legacy_ids_map.get(package_id, [])
            
            apps.append(app)
    return apps, legacy_ids_map

def fix_and_seed():
    logger.info("Starting Scheduler DB Fix & Seed...")
    
    try:
        apps, legacy_ids_map = load_apps_from_config()
        logger.info(f"Loaded {len(apps)} apps from configuration ({len(legacy_ids_map)} with legacy IDs).")

        with get_db_session() as session:
            # 1. Fix Schema
            logger.info("1. Checking/Fixing Schema...")
            # Check column type
            try:
                # This query works on MySQL/MariaDB to check column type
                result = session.execute(text("""
                    SELECT COLUMN_TYPE 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_SCHEMA = DATABASE() 
                    AND TABLE_NAME = 'reviews' 
                    AND COLUMN_NAME = 'content_hash'
                """))
                col_type = result.scalar()
                logger.info(f"Current content_hash type: {col_type}")
                
                if 'varchar(64)' not in str(col_type).lower():
                    logger.info("Altering content_hash to VARCHAR(64)...")
                    session.execute(text("ALTER TABLE reviews MODIFY content_hash VARCHAR(64)"))
                    session.commit()
                    logger.info("Schema altered.")
                else:
                    logger.info("Schema is already correct.")
            except Exception as e:
                logger.warning(f"Could not check/alter schema (might be permission or table missing): {e}")

            # 2. Seed Metadata
            logger.info("2. Seeding app_metadata...")
            
            # Check if legacy_ids column exists, add if not
            result = session.execute(text("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'app_metadata' 
                AND COLUMN_NAME = 'legacy_ids'
            """))
            has_legacy_ids = result.scalar() > 0
            
            if not has_legacy_ids:
                logger.info("Adding legacy_ids column to app_metadata...")
                session.execute(text("ALTER TABLE app_metadata ADD COLUMN legacy_ids JSON DEFAULT NULL"))
                session.commit()
                logger.info("legacy_ids column added.")
            else:
                logger.info("legacy_ids column already exists.")
            
            for app in apps:
                legacy_ids_json = json.dumps(app['legacy_ids']) if app['legacy_ids'] else None
                logger.info(f"Inserting/Updating {app['name']}... (legacy_ids: {len(app['legacy_ids'])} entries)")
                session.execute(text("""
                    INSERT INTO app_metadata (
                        package_id, company_code, company_name, group_code, priority, 
                        title, developer, genre, score, ratings, reviews, version, updated, last_collected, legacy_ids
                    ) VALUES (
                        :package_id, :code, :company, :group, :priority, 
                        :name, 'Developer', 'Finance', 0, 0, 0, '0.0.0', NOW(), NULL, :legacy_ids
                    ) ON DUPLICATE KEY UPDATE
                        company_name = VALUES(company_name),
                        group_code = VALUES(group_code),
                        priority = VALUES(priority),
                        legacy_ids = VALUES(legacy_ids)
                """), {
                    'package_id': app['package_id'],
                    'code': app['code'],
                    'company': app['company'],
                    'group': app['group'],
                    'priority': app['priority'],
                    'name': app['name'],
                    'legacy_ids': legacy_ids_json
                })
            
            session.commit()
            logger.info("Seeding completed.")
            
            # Verify
            count = session.execute(text("SELECT COUNT(*) FROM app_metadata")).scalar()
            logger.info(f"Final app_metadata row count: {count}")

    except Exception as e:
        logger.error(f"Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    fix_and_seed()
