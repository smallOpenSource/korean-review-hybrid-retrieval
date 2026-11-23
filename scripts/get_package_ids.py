import os
import sys
from sqlalchemy import create_engine, text
from app.config.settings import get_settings

def get_package_ids():
    settings = get_settings().mysql
    engine = create_engine(settings.connection_string)
    
    targets = ['sec_b', 'card_b', 'ins_h', 'bank_q']
    
    with engine.connect() as conn:
        # Check columns first
        query = text("SELECT * FROM app_metadata LIMIT 1")
        result = conn.execute(query).mappings().fetchone()
        if result:
            print(f"Columns: {list(result.keys())}")
            
        for code in targets:
            query = text("SELECT * FROM app_metadata WHERE company_code = :code")
            result = conn.execute(query, {'code': code}).mappings().fetchone()
            if result:
                # Try to find package_name or similar
                pkg = result.get('package_name') or result.get('package_id') or result.get('app_id')
                print(f"{code}:{pkg}")
            else:
                print(f"{code}:NOT_FOUND")

if __name__ == "__main__":
    # Add project root to path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    get_package_ids()
