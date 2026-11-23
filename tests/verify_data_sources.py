
import os
import sys
from dotenv import load_dotenv
import pymysql
from opensearchpy import OpenSearch

# Load env
load_dotenv()

def verify_mysql():
    print("--- Verifying MySQL ---")
    try:
        conn = pymysql.connect(
            host='127.0.0.1',
            user=os.getenv('MYSQL_USER'),
            password=os.getenv('MYSQL_PASSWORD'),
            database=os.getenv('MYSQL_DATABASE'),
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        with conn.cursor() as cursor:
            # Check tables
            cursor.execute("SHOW TABLES")
            tables = [list(row.values())[0] for row in cursor.fetchall()]
            print(f"Tables found: {tables}")
            
            # Check app_metadata
            if 'app_metadata' in tables:
                cursor.execute("SELECT count(*) as count FROM app_metadata")
                print(f"app_metadata count: {cursor.fetchone()['count']}")
                
            # Check mart_app_stats_yearly
            if 'mart_app_stats_yearly' in tables:
                cursor.execute("SELECT count(*) as count FROM mart_app_stats_yearly")
                print(f"mart_app_stats_yearly count: {cursor.fetchone()['count']}")
                
            # Check reviews
            if 'reviews' in tables:
                # Just check partition p2025 if possible or limit
                cursor.execute("SELECT count(*) as count FROM reviews WHERE at >= '2025-01-01'")
                print(f"reviews (2025+) count: {cursor.fetchone()['count']}")
                
        conn.close()
        print("MySQL Verification: SUCCESS")
    except Exception as e:
        print(f"MySQL Verification: FAILED - {e}")

def verify_opensearch():
    print("\n--- Verifying OpenSearch ---")
    try:
        hosts = os.getenv('OPENSEARCH_HOSTS', 'https://localhost:9200').split(',')
        auth = (os.environ['OPENSEARCH_USER'], os.environ['OPENSEARCH_PASSWORD'])
        
        client = OpenSearch(
            hosts=hosts,
            http_auth=auth,
            verify_certs=False,
            ssl_show_warn=False
        )
        
        # Check indices
        indices = client.cat.indices(format='json')
        index_names = [i['index'] for i in indices]
        print(f"Indices found: {index_names}")
        
        # Check app_reviews
        if 'app_reviews' in index_names:
            count = client.count(index='app_reviews')['count']
            print(f"app_reviews count: {count}")
            
        # Check review_analytics
        if 'review_analytics' in index_names:
            count = client.count(index='review_analytics')['count']
            print(f"review_analytics count: {count}")
            
        print("OpenSearch Verification: SUCCESS")
    except Exception as e:
        print(f"OpenSearch Verification: FAILED - {e}")

if __name__ == "__main__":
    verify_mysql()
    verify_opensearch()
