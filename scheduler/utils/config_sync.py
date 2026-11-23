"""
YAML to Database config synchronization.
Syncs legacy_ids from apps_config.yaml to app_metadata table.

This module is called on scheduler startup to ensure YAML is the
single source of truth for legacy app ID mappings.
"""
import json
import logging
from pathlib import Path

import yaml
from sqlalchemy import text

from scheduler.utils.database import get_db_session

logger = logging.getLogger(__name__)


def sync_legacy_ids_to_db() -> int:
    """
    Sync legacy_ids from apps_config.yaml to database.
    Only updates legacy_ids column, preserves other data.
    
    Returns:
        Number of apps synced
    """
    config_path = Path(__file__).parent.parent / 'config' / 'apps_config.yaml'
    
    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}")
        return 0
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Build legacy_ids mapping from app_id_history section
    legacy_ids_map = {}
    for entry in config.get('app_id_history', []):
        current_id = entry.get('current')
        previous = [p.get('id') for p in entry.get('previous', []) if p.get('id')]
        if current_id and previous:
            legacy_ids_map[current_id] = previous
    
    if not legacy_ids_map:
        logger.info("No legacy IDs found in config")
        return 0
    
    logger.info(f"Syncing {len(legacy_ids_map)} apps with legacy IDs...")
    
    synced_count = 0
    
    with get_db_session() as session:
        # Ensure legacy_ids column exists
        result = session.execute(text("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'app_metadata' 
            AND COLUMN_NAME = 'legacy_ids'
        """))
        if result.scalar() == 0:
            logger.info("Adding legacy_ids column to app_metadata...")
            session.execute(text(
                "ALTER TABLE app_metadata ADD COLUMN legacy_ids JSON DEFAULT NULL"
            ))
            session.commit()
            logger.info("legacy_ids column added")
        
        # Update legacy_ids for each app
        for package_id, legacy_ids in legacy_ids_map.items():
            result = session.execute(text("""
                UPDATE app_metadata 
                SET legacy_ids = :legacy_ids 
                WHERE package_id = :package_id
            """), {
                'package_id': package_id,
                'legacy_ids': json.dumps(legacy_ids)
            })
            if result.rowcount > 0:
                synced_count += 1
                logger.debug(f"Synced legacy_ids for {package_id}: {legacy_ids}")
        
        session.commit()
    
    logger.info(f"Synced legacy_ids for {synced_count} apps")
    return synced_count
