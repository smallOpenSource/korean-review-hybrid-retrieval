
import os
import sys
from dotenv import load_dotenv
import pymysql
from opensearchpy import OpenSearch

# Load env
load_dotenv()

TEST_APP_ID = '99999'

def delete_mysql_data():
    print("--- Deleting from MySQL ---")
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
            # Check if exists
            cursor.execute("SELECT * FROM app_metadata WHERE package_id = %s", (TEST_APP_ID,))
            if cursor.fetchone():
                print(f"Found Test App in MySQL. Deleting...")
                cursor.execute("DELETE FROM app_metadata WHERE package_id = %s", (TEST_APP_ID,))
                conn.commit()
                print("Deleted from app_metadata.")
            else:
                print("Test App not found in MySQL.")
                
        conn.close()
        print("MySQL Deletion: SUCCESS")
    except Exception as e:
        print(f"MySQL Deletion: FAILED - {e}")

def delete_opensearch_data():
    print("\n--- Deleting from OpenSearch ---")
    try:
        hosts = os.getenv('OPENSEARCH_HOSTS', 'https://localhost:9200').split(',')
        auth = (os.environ['OPENSEARCH_USER'], os.environ['OPENSEARCH_PASSWORD'])
        
        client = OpenSearch(
            hosts=hosts,
            http_auth=auth,
            verify_certs=False,
            ssl_show_warn=False
        )
        
        # Delete by query
        query = {
            "query": {
                "term": {
                    "app_id": TEST_APP_ID
                }
            }
        }
        
        response = client.delete_by_query(index='app_reviews', body=query)
        print(f"Deleted {response.get('deleted', 0)} documents from app_reviews.")
            
        print("OpenSearch Deletion: SUCCESS")
    except Exception as e:
        print(f"OpenSearch Deletion: FAILED - {e}")

if __name__ == "__main__":
    delete_mysql_data()
    delete_opensearch_data()
