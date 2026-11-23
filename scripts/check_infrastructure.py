#!/usr/bin/env python3
"""
Check current state of MariaDB and OpenSearch infrastructure.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from app.config.settings import get_settings
from app.core.mysql_client import get_mysql_client
from app.core.opensearch_client import get_opensearch_client

def check_mariadb():
    """Check MariaDB databases and tables."""
    print("=" * 80)
    print("MariaDB Status Check")
    print("=" * 80)
    
    settings = get_settings().mysql
    print(f"\nConnection Info:")
    print(f"  Host: {settings.host}:{settings.port}")
    print(f"  Database: {settings.database}")
    print(f"  User: {settings.user}")
    
    try:
        mysql_client = get_mysql_client()
        conn = mysql_client.get_connection()
        cursor = conn.cursor()
        
        # Show databases
        print("\n[Databases]")
        cursor.execute("SHOW DATABASES")
        databases = cursor.fetchall()
        for db in databases:
            print(f"  - {db[0]}")
        
        # Check if target database exists
        cursor.execute(f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{settings.database}'")
        db_exists = cursor.fetchone()
        
        if db_exists:
            print(f"\n✓ Database '{settings.database}' exists")
            
            # Show tables in target database
            cursor.execute(f"USE {settings.database}")
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            print(f"\n[Tables in '{settings.database}']")
            if tables:
                for table in tables:
                    table_name = table[0]
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    print(f"  - {table_name}: {count:,} rows")
                    
                    # Show table structure for important tables
                    if table_name in ['reviews', 'app_metadata', 'job_runs']:
                        print(f"\n    Structure of '{table_name}':")
                        cursor.execute(f"DESCRIBE {table_name}")
                        columns = cursor.fetchall()
                        for col in columns[:5]:  # Show first 5 columns
                            print(f"      {col[0]}: {col[1]}")
                        if len(columns) > 5:
                            print(f"      ... and {len(columns) - 5} more columns")
            else:
                print("  (No tables found)")
        else:
            print(f"\n✗ Database '{settings.database}' does NOT exist")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"\n✗ MariaDB connection failed: {e}")
        return False
    
    return True


def check_opensearch():
    """Check OpenSearch cluster and indices."""
    print("\n" + "=" * 80)
    print("OpenSearch Status Check")
    print("=" * 80)
    
    settings = get_settings().opensearch
    print(f"\nConnection Info:")
    print(f"  Hosts: {', '.join(settings.hosts)}")
    print(f"  User: {settings.user}")
    print(f"  SSL Verify: {settings.ssl_verify}")
    
    try:
        os_client = get_opensearch_client()
        
        # Cluster health
        print("\n[Cluster Health]")
        health = os_client.health_check()
        print(f"  Status: {health.get('status', 'unknown')}")
        print(f"  Nodes: {health.get('number_of_nodes', 0)}")
        print(f"  Active Shards: {health.get('active_shards', 0)}")
        
        # List all indices
        print("\n[Indices]")
        client = os_client.sync_client
        indices = client.cat.indices(format='json')
        
        if indices:
            print(f"  Total indices: {len(indices)}")
            for idx in indices:
                index_name = idx.get('index', '')
                docs_count = idx.get('docs.count', '0')
                store_size = idx.get('store.size', '0')
                health = idx.get('health', '')
                
                # Skip system indices
                if index_name.startswith('.'):
                    continue
                    
                print(f"\n  - {index_name}")
                print(f"    Health: {health}")
                print(f"    Documents: {docs_count}")
                print(f"    Size: {store_size}")
                
                # Get mapping for application indices
                if index_name in ['app_reviews', 'review_analytics']:
                    try:
                        mapping = client.indices.get_mapping(index=index_name)
                        properties = mapping.get(index_name, {}).get('mappings', {}).get('properties', {})
                        print(f"    Fields: {len(properties)}")
                        
                        # Show some key fields
                        key_fields = ['review_id', 'content_embedding', 'sentiment', 'complaint']
                        for field in key_fields:
                            if field in properties:
                                field_type = properties[field].get('type', properties[field])
                                print(f"      {field}: {field_type}")
                    except Exception as e:
                        print(f"    (Could not get mapping: {e})")
        else:
            print("  (No indices found)")
            
    except Exception as e:
        print(f"\n✗ OpenSearch connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


def main():
    """Main check function."""
    print("\n" + "=" * 80)
    print("Infrastructure Status Check")
    print("=" * 80)
    print()
    
    mariadb_ok = check_mariadb()
    opensearch_ok = check_opensearch()
    
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"MariaDB: {'✓ OK' if mariadb_ok else '✗ FAILED'}")
    print(f"OpenSearch: {'✓ OK' if opensearch_ok else '✗ FAILED'}")
    print()
    
    if mariadb_ok and opensearch_ok:
        print("✓ All infrastructure components are accessible")
        return 0
    else:
        print("✗ Some infrastructure components are not accessible")
        return 1


if __name__ == '__main__':
    sys.exit(main())
